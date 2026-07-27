"""Weber Digital Premium datu pārveidošana GMPS Product modelī.

Weber Digital Premium CSV faili ir produktu aprakstu un mārketinga satura avots.
Tie nav uzskatāmi par gala SKU avotu. Gala SKU tiek piešķirts vēlāk, sasaistot
Weber aprakstu ar piegādātāja produktu.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Any

from src.gmps.models import Product, ProductDocument


class WeberMapperError(Exception):
    """Pamata kļūda Weber datu kartēšanas laikā."""


class WeberMissingNameError(WeberMapperError):
    """Weber ierakstam nav atrasts produkta nosaukums."""


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "import_id": ("import id", "digital premium id", "product id", "id"),
    "article_number": (
        "article number", "article number acc sp 1", "article number acc sp",
        "article no", "article no.", "catalogue number", "catalog number",
        "item number", "material number",
    ),
    "ean": (
        "ean", "ean code", "ean code acc sp 1", "ean code acc sp",
        "barcode", "gtin", "gtin13",
    ),
    "name": (
        "product title", "product name", "product title line 1",
        "product title line 1 accessories", "title", "name",
    ),
    "title_line_1": (
        "product title line 1", "product title line 1 accessories",
        "product title line 1 gas", "product title line 1 electric",
        "product title line 1 pellet", "product title line 1 griddle",
    ),
    "title_line_2": (
        "product title line 2", "product title line 2 accessories",
        "product title line 2 gas", "product title line 2 electric",
        "product title line 2 pellet", "product title line 2 griddle",
    ),
    "description": (
        "product description", "description", "long description",
        "marketing description", "english description", "description en",
    ),
    "short_description": (
        "short description", "short product description",
        "product introduction", "intro", "teaser",
    ),
    "features": ("features", "product features", "key features", "feature bullets"),
    "benefits": ("benefits", "product benefits", "customer benefits", "key benefits"),
    "sales_arguments": (
        "sales arguments", "sales argument", "selling points",
        "key selling points", "usp", "usps",
    ),
    "series": ("series", "product series", "range", "product range", "family", "barbecue series"),
    "model": ("model", "model name", "model number", "barbecue code"),
    "product_type": ("product type", "type", "product category", "category"),
    "product_subtype": ("product subtype", "subtype", "sub type", "subcategory", "sub category"),
    "fuel_type": ("fuel type", "fuel", "energy source"),
    "colour": ("colour", "color", "product colour", "product color"),
    "material": ("material", "main material"),
    "warranty": ("warranty", "guarantee", "warranty information"),
    "width": ("width", "product width", "width cm"),
    "height": ("height", "product height", "height cm"),
    "depth": ("depth", "product depth", "depth cm", "length", "product length"),
    "weight": ("weight", "net weight", "gross weight", "weight kg"),
    "compatibility": ("compatibility", "compatible with", "fits", "suitable for"),
    "package_contents": ("package contents", "included", "included in box", "box contents"),
    "amount_packaging": ("amount packaging", "minimum order quantity", "packaging amount"),
}

SPECIFICATION_FIELDS: dict[str, str] = {
    "series": "Sērija",
    "model": "Modelis",
    "product_type": "Produkta veids",
    "product_subtype": "Produkta apakšveids",
    "fuel_type": "Enerģijas avots",
    "colour": "Krāsa",
    "material": "Materiāls",
    "width": "Platums",
    "height": "Augstums",
    "depth": "Dziļums",
    "weight": "Svars",
    "amount_packaging": "Iepakojuma daudzums",
    "ean": "EAN",
}


def normalize_key(value: str) -> str:
    text = str(value).replace("\ufeff", "").casefold()
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_row(row: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = normalize_key(str(key))
        if normalized_key:
            normalized[normalized_key] = clean_value(value)
    return normalized


def get_value(row: Mapping[str, str], field_name: str, *, default: str = "") -> str:
    for alias in FIELD_ALIASES.get(field_name, (field_name,)):
        value = row.get(normalize_key(alias), "")
        if value:
            return value

    dynamic_patterns: dict[str, tuple[str, ...]] = {
        "article_number": (r"article number acc sp \d+", r"article number \d+", r"article no \d+"),
        "ean": (r"ean code acc sp \d+", r"ean code \d+", r"barcode \d+"),
        "title_line_1": (r"product title line 1(?: .+)?",),
        "title_line_2": (r"product title line 2(?: .+)?",),
    }
    for pattern in dynamic_patterns.get(field_name, ()):
        for column, value in row.items():
            if value and re.fullmatch(pattern, column):
                return value
    return default


def split_list_value(value: str) -> list[str]:
    if not value:
        return []
    prepared = value.replace("\r\n", "\n").replace("\r", "\n")
    prepared = prepared.replace("•", "\n").replace("·", "\n")
    result: list[str] = []
    for part in re.split(r"\n|;|\|", prepared):
        item = clean_value(part).lstrip("-–—").strip()
        if item and item not in result:
            result.append(item)
    return result


def collect_numbered_values(row: Mapping[str, str], prefixes: Iterable[str]) -> list[str]:
    normalized_prefixes = tuple(normalize_key(prefix) for prefix in prefixes)
    matches: list[tuple[int, str]] = []
    for column, value in row.items():
        if not value:
            continue
        for prefix in normalized_prefixes:
            match = re.fullmatch(rf"{re.escape(prefix)}\s*(\d+)", column)
            if match:
                matches.append((int(match.group(1)), value))
                break
    matches.sort(key=lambda item: item[0])
    result: list[str] = []
    for _, value in matches:
        for item in split_list_value(value):
            if item not in result:
                result.append(item)
    return result


def merge_unique(*groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            cleaned = clean_value(value)
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
    return result


def build_matching_name(*, product_title: str, title_line_1: str, title_line_2: str) -> str:
    if product_title:
        return product_title
    return " - ".join(part for part in (title_line_1, title_line_2) if part)


def detect_product_type(row: Mapping[str, str], *, source_category: str = "") -> str:
    searchable_text = " ".join((
        get_value(row, "name"),
        get_value(row, "title_line_1"),
        get_value(row, "title_line_2"),
        get_value(row, "product_type"),
        get_value(row, "product_subtype"),
        get_value(row, "series"),
        get_value(row, "fuel_type"),
        source_category,
    )).casefold()
    category = normalize_key(source_category)

    category_map = {
        "bbq kitchen": "outdoor_kitchen",
        "accessories": "accessory",
        "accessory": "accessory",
        "spare parts": "replacement_part",
        "spare part": "replacement_part",
        "replacement parts": "replacement_part",
        "replacement part": "replacement_part",
        "electric": "electric_grill",
        "electric grills": "electric_grill",
        "gas": "gas_grill",
        "gas grills": "gas_grill",
        "griddles": "griddle",
        "griddle": "griddle",
        "wood": "pellet_grill",
        "pellet": "pellet_grill",
        "pellet grills": "pellet_grill",
    }
    if category in category_map:
        return category_map[category]

    keyword_groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("replacement_part", ("spare part", "replacement part", "rezerves daļa", "rezerves dala")),
        ("outdoor_kitchen", ("bbq kitchen", "door module", "drawer module", "fridge module", "sink module", "outdoor fridge")),
        ("accessory", ("accessory", "accessories", "aksesuārs", "aksesuars")),
        ("griddle", ("griddle", "plancha", "slate")),
        ("pellet_grill", ("pellet", "smokefire", "smoque", "searwood", "granulu")),
        ("smoker", ("smoker", "smokey mountain", "kūpinātava", "kupinatava")),
        ("electric_grill", ("electric", "lumin", "pulse", "elektriskais", "elektriska")),
        ("charcoal_grill", ("charcoal", "kettle", "smokey joe", "kokogļu", "kokoglu")),
        ("gas_grill", ("gas grill", "gas barbecue", "spirit", "genesis", "summit", "traveler", "weber q", "gāzes", "gazes")),
    )
    for product_type, keywords in keyword_groups:
        if any(term in searchable_text for term in keywords):
            return product_type
    return "other"


def build_specifications(row: Mapping[str, str]) -> dict[str, str]:
    specifications: dict[str, str] = {}
    for field_name, output_name in SPECIFICATION_FIELDS.items():
        value = get_value(row, field_name)
        if value:
            specifications[output_name] = value
    return specifications


def find_url_values(row: Mapping[str, str], keywords: Iterable[str]) -> list[str]:
    normalized_keywords = tuple(normalize_key(keyword) for keyword in keywords)
    result: list[str] = []
    for column, value in row.items():
        if not value or not any(keyword in column for keyword in normalized_keywords):
            continue
        for candidate in split_list_value(value):
            if candidate.startswith(("http://", "https://")) and candidate not in result:
                result.append(candidate)
    return result


def build_validation_warnings(*, import_id: str, name: str, description: str, product_type: str) -> list[str]:
    warnings: list[str] = []
    if not import_id:
        warnings.append("Weber apraksta ierakstam nav Import ID.")
    if not name:
        warnings.append("Weber apraksta ierakstam nav produkta nosaukuma.")
    if not description:
        warnings.append("Weber avota datos nav produkta apraksta.")
    if product_type == "other":
        warnings.append("Produkta veidu neizdevās noteikt automātiski.")
    warnings.append(
        "Weber Digital Premium ieraksts vēl nav piesaistīts "
        "piegādātāja produktam ar gala SKU."
    )
    return warnings


def build_technical_identifier(*, import_id: str, article_number: str, name: str) -> str:
    if import_id:
        return import_id
    if article_number:
        return article_number
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12].upper()
    return f"WEBER-DESCRIPTION-{digest}"


def map_weber_row(
    row: Mapping[str, Any],
    *,
    source_category: str = "",
    source_filename: str = "",
) -> Product:
    normalized_row = normalize_row(row)
    product_title = get_value(normalized_row, "name")
    title_line_1 = get_value(normalized_row, "title_line_1")
    title_line_2 = get_value(normalized_row, "title_line_2")
    name = build_matching_name(
        product_title=product_title,
        title_line_1=title_line_1,
        title_line_2=title_line_2,
    )
    if not name:
        raise WeberMissingNameError("Weber apraksta rindā nav atrasts produkta nosaukums.")

    import_id = get_value(normalized_row, "import_id")
    article_number = get_value(normalized_row, "article_number")
    ean = get_value(normalized_row, "ean")
    description = get_value(normalized_row, "description")
    short_description = get_value(normalized_row, "short_description")
    product_type = detect_product_type(normalized_row, source_category=source_category)

    all_features = merge_unique(
        split_list_value(get_value(normalized_row, "features")),
        collect_numbered_values(normalized_row, ("Feature", "Product feature", "Key feature")),
        split_list_value(get_value(normalized_row, "benefits")),
        collect_numbered_values(normalized_row, ("Benefit", "Product benefit", "Customer benefit")),
        split_list_value(get_value(normalized_row, "sales_arguments")),
        collect_numbered_values(normalized_row, ("Sales argument", "Selling point", "USP")),
    )

    technical_identifier = build_technical_identifier(
        import_id=import_id,
        article_number=article_number,
        name=name,
    )

    product = Product(
        brand="Weber",
        sku=technical_identifier,
        ean=ean,
        mpn=article_number,
        import_id=import_id,
        supplier_id="",
        name=name,
        original_name=name,
        product_type=product_type,
        product_subtype=get_value(normalized_row, "product_subtype"),
        series=get_value(normalized_row, "series"),
        model=get_value(normalized_row, "model"),
        supplier_description=description,
        supplier_short_description=short_description,
        specifications=build_specifications(normalized_row),
        compatibility=split_list_value(get_value(normalized_row, "compatibility")),
        package_contents=split_list_value(get_value(normalized_row, "package_contents")),
        source_file=source_filename,
        source_category=source_category,
        validation_warnings=build_validation_warnings(
            import_id=import_id,
            name=name,
            description=description,
            product_type=product_type,
        ),
        raw_data=dict(row),
    )

    product.attributes["record_type"] = "weber_description"
    product.attributes["temporary_sku"] = "true"
    product.attributes["matching_name"] = name
    if product_title:
        product.attributes["product_title"] = product_title
    if title_line_1:
        product.attributes["title_line_1"] = title_line_1
    if title_line_2:
        product.attributes["title_line_2"] = title_line_2
    if article_number:
        product.attributes["weber_article_number"] = article_number
    if import_id:
        product.attributes["weber_import_id"] = import_id
    if ean:
        product.attributes["weber_ean"] = ean

    for feature in all_features:
        product.add_feature(feature)

    image_urls = find_url_values(
        normalized_row,
        ("image", "photo", "picture", "packshot", "visual", "url"),
    )
    for position, image_url in enumerate(image_urls):
        product.add_image(
            url=image_url,
            alt_text=product.display_name,
            position=position,
        )

    document_urls = find_url_values(
        normalized_row,
        ("document", "manual", "instruction", "brochure", "datasheet", "pdf"),
    )
    for document_url in document_urls:
        product.documents.append(
            ProductDocument(
                url=document_url,
                title=f"{product.display_name} dokuments",
                document_type="supplier",
            )
        )

    product.videos.extend(
        find_url_values(normalized_row, ("video", "youtube", "vimeo"))
    )
    return product


def map_weber_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_category: str = "",
    source_filename: str = "",
    skip_invalid: bool = False,
) -> list[Product]:
    products: list[Product] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            product = map_weber_row(
                row,
                source_category=source_category,
                source_filename=source_filename,
            )
        except WeberMapperError as exc:
            if skip_invalid:
                continue
            source_text = f" failā {source_filename!r}" if source_filename else ""
            raise WeberMapperError(
                f"Neizdevās kartēt Weber rindas numuru {row_number}{source_text}: {exc}"
            ) from exc
        products.append(product)
    return products
