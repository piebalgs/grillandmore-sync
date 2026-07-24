"""Parser for Weber Digital Premium product CSV exports.

The source file is UTF-16 LE and tab-separated, despite the .csv extension.
This module reads the source safely and converts each row into a structured
ProductDescription object without changing WooCommerce.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {
    "Barbecue code",
    "Product title",
    "Product description",
}


class DescriptionParseError(ValueError):
    """Raised when the source file cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class ConsumerBenefit:
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ProductFeature:
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ProductDescription:
    sku: str
    import_id: str
    title: str
    title_line_1: str = ""
    title_line_2: str = ""
    title_line_3: str = ""
    source_description: str = ""
    sales_arguments: tuple[str, ...] = ()
    consumer_benefits: tuple[ConsumerBenefit, ...] = ()
    product_features: tuple[ProductFeature, ...] = ()
    specifications: dict[str, str] = field(default_factory=dict)
    raw: dict[str, str] = field(default_factory=dict, repr=False, compare=False)


SPECIFICATION_COLUMNS = {
    "barbecue_type": "Type barbecue",
    "guarantee": "Guarantee years",
    "grate_size": "Grate tekst",
    "grate_shape": "Grate shape",
    "hamburger_capacity": "Hamburgers per grate",
    "color": "Color text",
    "dimensions_open_lid": "Product size open lid",
    "dimensions_closed_lid": "Product size closed lid",
    "net_weight": "Net weight",
    "packaging_dimensions": "Packaging size",
    "gross_weight": "Gross weight",
}


def _clean(value: object) -> str:
    """Normalize a cell while preserving its wording and punctuation."""
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def _clean_row(row: dict[str, object]) -> dict[str, str]:
    return {
        _clean(key).lstrip("\ufeff"): _clean(value)
        for key, value in row.items()
        if key is not None
    }


def _validate_headers(fieldnames: Iterable[str] | None) -> None:
    if not fieldnames:
        raise DescriptionParseError("Failā nav atrasta galvenes rinda.")

    normalized = {_clean(name).lstrip("\ufeff") for name in fieldnames}
    missing = sorted(REQUIRED_COLUMNS - normalized)
    if missing:
        raise DescriptionParseError(
            "Failā trūkst obligāto kolonnu: " + ", ".join(missing)
        )


def _numbered_values(row: dict[str, str], prefix: str, count: int) -> tuple[str, ...]:
    values: list[str] = []
    for number in range(1, count + 1):
        value = row.get(f"{prefix}{number}", "")
        if value:
            values.append(value)
    return tuple(values)


def _consumer_benefits(row: dict[str, str]) -> tuple[ConsumerBenefit, ...]:
    benefits: list[ConsumerBenefit] = []
    for number in range(1, 5):
        title = row.get(f"PFC consumer benefit title {number}", "")
        description = row.get(f"PFC consumer benefit description {number}", "")
        if title or description:
            benefits.append(ConsumerBenefit(title=title, description=description))
    return tuple(benefits)


def _product_features(row: dict[str, str]) -> tuple[ProductFeature, ...]:
    features: list[ProductFeature] = []
    for number in range(1, 6):
        title = row.get(f"PFC feature title {number}", "")
        description = row.get(f"PFC feature description {number}", "")
        if title or description:
            features.append(ProductFeature(title=title, description=description))
    return tuple(features)


def _specifications(row: dict[str, str]) -> dict[str, str]:
    return {
        key: row[column]
        for key, column in SPECIFICATION_COLUMNS.items()
        if row.get(column)
    }


def _parse_product(row: dict[str, str], row_number: int) -> ProductDescription:
    sku = row.get("Barbecue code", "")
    title = row.get("Product title", "") or row.get("Product title line 1", "")

    if not sku:
        raise DescriptionParseError(
            f"{row_number}. datu rindā nav norādīts 'Barbecue code'."
        )
    if not title:
        raise DescriptionParseError(
            f"{row_number}. datu rindā nav norādīts produkta nosaukums."
        )

    return ProductDescription(
        sku=sku,
        import_id=row.get("Import ID", ""),
        title=title,
        title_line_1=row.get("Product title line 1", ""),
        title_line_2=row.get("Product title line 2", ""),
        title_line_3=row.get("Product title line 3", ""),
        source_description=row.get("Product description", ""),
        sales_arguments=_numbered_values(row, "Sales arguments line ", 15),
        consumer_benefits=_consumer_benefits(row),
        product_features=_product_features(row),
        specifications=_specifications(row),
        raw=row,
    )


def load_products(path: str | Path) -> list[ProductDescription]:
    """Load all products from a Weber Digital Premium gas-grill export."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"CSV fails nav atrasts: {source}")

    products: list[ProductDescription] = []
    seen_skus: set[str] = set()

    try:
        with source.open("r", encoding="utf-16", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            _validate_headers(reader.fieldnames)

            for row_number, source_row in enumerate(reader, start=2):
                row = _clean_row(source_row)
                if not any(row.values()):
                    continue

                product = _parse_product(row, row_number)
                if product.sku in seen_skus:
                    raise DescriptionParseError(
                        f"Dublēts Barbecue code '{product.sku}' "
                        f"({row_number}. datu rinda)."
                    )

                seen_skus.add(product.sku)
                products.append(product)
    except UnicodeError as exc:
        raise DescriptionParseError(
            "Failu neizdevās nolasīt kā UTF-16 tekstu."
        ) from exc
    except csv.Error as exc:
        raise DescriptionParseError(f"CSV struktūras kļūda: {exc}") from exc

    if not products:
        raise DescriptionParseError("Failā nav atrasts neviens produkts.")

    return products


def products_by_sku(path: str | Path) -> dict[str, ProductDescription]:
    """Return parsed products indexed by SKU."""
    return {product.sku: product for product in load_products(path)}


def _print_preview(product: ProductDescription) -> None:
    print(f"SKU: {product.sku}")
    print(f"Nosaukums: {product.title}")
    print(f"Apraksts: {product.source_description or '-'}")
    print(f"Pārdošanas argumenti: {len(product.sales_arguments)}")
    print(f"Patērētāja ieguvumi: {len(product.consumer_benefits)}")
    print(f"Produkta funkcijas: {len(product.product_features)}")
    print("Specifikācijas:")
    for key, value in product.specifications.items():
        print(f"  - {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pārbauda Weber gāzes grilu aprakstu CSV parseri."
    )
    parser.add_argument("csv_path", help="Ceļš uz Digital Premium Gas CSV failu")
    parser.add_argument(
        "--sku",
        help="Parādīt konkrētu produktu; ja nav norādīts, rāda pirmo produktu",
    )
    args = parser.parse_args()

    try:
        products = load_products(args.csv_path)
    except (FileNotFoundError, DescriptionParseError) as exc:
        parser.error(str(exc))

    print(f"Atrasti produkti: {len(products)}")

    if args.sku:
        product = next((item for item in products if item.sku == args.sku), None)
        if product is None:
            parser.error(f"SKU '{args.sku}' failā nav atrasts.")
    else:
        product = products[0]

    print()
    _print_preview(product)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
