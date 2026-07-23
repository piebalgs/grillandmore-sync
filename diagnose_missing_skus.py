from __future__ import annotations

import csv
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from src import supplier, woocommerce


Product = dict[str, Any]

REPORT_DIRECTORY = Path("reports")
REPORT_PATH = REPORT_DIRECTORY / "missing_sku_diagnosis.csv"

SIMILAR_SKU_LIMIT = 3
SIMILAR_NAME_LIMIT = 3
MINIMUM_SKU_SIMILARITY = 0.55
MINIMUM_NAME_SIMILARITY = 0.45


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_sku(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_name(value: Any) -> str:
    return " ".join(
        normalize_text(value).lower().split()
    )


def product_sku(product: Product) -> str:
    return normalize_sku(
        product.get("sku")
        or product.get("catalogue_number")
        or product.get("catalog_number")
    )


def product_name(product: Product) -> str:
    return normalize_text(product.get("name"))


def product_status(product: Product) -> str:
    return normalize_text(product.get("status"))


def product_type(product: Product) -> str:
    return normalize_text(product.get("type"))


def product_id(product: Product) -> int:
    try:
        return int(product.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def similarity(first: str, second: str) -> float:
    if not first or not second:
        return 0.0

    return SequenceMatcher(
        None,
        first,
        second,
    ).ratio()


def build_product_map(
    products: Iterable[Product],
) -> dict[str, Product]:
    result: dict[str, Product] = {}

    for product in products:
        sku = product_sku(product)

        if sku and sku not in result:
            result[sku] = product

    return result


def load_products_by_status(
    status: str,
) -> list[Product]:
    products: list[Product] = []
    page = 1

    print(
        f"Nolasa WooCommerce produktus ar statusu "
        f"'{status}'..."
    )

    while True:
        response = woocommerce._request(
            method="GET",
            url=(
                f"{woocommerce.BASE_URL}"
                "/wp-json/wc/v3/products"
            ),
            params={
                "per_page": 100,
                "page": page,
                "status": status,
            },
        )

        page_products = response.json()

        if not isinstance(page_products, list):
            raise RuntimeError(
                "WooCommerce API atgrieza neparedzētu "
                "produktu sarakstu."
            )

        if not page_products:
            break

        products.extend(page_products)

        print(
            f"  Nolasīta {page}. lapa — "
            f"kopā {len(products)} produkti."
        )

        if len(page_products) < 100:
            break

        page += 1

    return products


def load_product_variations(
    parent_product_id: int,
) -> list[Product]:
    variations: list[Product] = []
    page = 1

    while True:
        response = woocommerce._request(
            method="GET",
            url=(
                f"{woocommerce.BASE_URL}"
                f"/wp-json/wc/v3/products/"
                f"{parent_product_id}/variations"
            ),
            params={
                "per_page": 100,
                "page": page,
                "status": "any",
            },
        )

        page_variations = response.json()

        if not isinstance(page_variations, list):
            raise RuntimeError(
                "WooCommerce API atgrieza neparedzētu "
                "variāciju sarakstu."
            )

        if not page_variations:
            break

        for variation in page_variations:
            if isinstance(variation, dict):
                variation["_parent_product_id"] = (
                    parent_product_id
                )
                variations.append(variation)

        if len(page_variations) < 100:
            break

        page += 1

    return variations


def load_all_variations(
    products: Iterable[Product],
) -> list[Product]:
    variable_products = [
        product
        for product in products
        if product_type(product) == "variable"
        and product_id(product) > 0
    ]

    variations: list[Product] = []
    total = len(variable_products)

    print()
    print(
        f"Pārbauda variācijas "
        f"({total} mainīgie produkti)..."
    )

    for index, product in enumerate(
        variable_products,
        start=1,
    ):
        current_id = product_id(product)

        print(
            f"  [{index}/{total}] "
            f"{product_name(product)}"
        )

        variations.extend(
            load_product_variations(current_id)
        )

    print(
        f"WooCommerce atrastas "
        f"{len(variations)} variācijas."
    )

    return variations


def find_similar_products(
    target_value: str,
    products: Iterable[Product],
    value_getter,
    minimum_similarity: float,
    limit: int,
) -> list[tuple[float, Product]]:
    matches: list[tuple[float, Product]] = []

    for product in products:
        candidate_value = value_getter(product)

        score = similarity(
            target_value,
            candidate_value,
        )

        if score >= minimum_similarity:
            matches.append((score, product))

    matches.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return matches[:limit]


def format_matches(
    matches: Iterable[tuple[float, Product]],
) -> str:
    parts: list[str] = []

    for score, product in matches:
        parts.append(
            f"{product_sku(product)} | "
            f"{product_name(product)} | "
            f"{score:.0%}"
        )

    return " || ".join(parts)


def determine_diagnosis(
    normal_product: Product | None,
    trash_product: Product | None,
    variation: Product | None,
    similar_skus: list[tuple[float, Product]],
    similar_names: list[tuple[float, Product]],
) -> str:
    if normal_product is not None:
        return (
            "Produkts ir atrodams WooCommerce "
            "galveno produktu sarakstā."
        )

    if trash_product is not None:
        return "Produkts atrodas WooCommerce miskastē."

    if variation is not None:
        return (
            "SKU ir WooCommerce produkta variācijai, "
            "nevis galvenajam produktam."
        )

    if similar_skus:
        return (
            "Precīzs SKU nav atrasts, bet ir līdzīgi SKU. "
            "Iespējama SKU maiņa vai ievades kļūda."
        )

    if similar_names:
        return (
            "Precīzs SKU nav atrasts, bet ir līdzīgs "
            "produkta nosaukums. Iespējams, produkts "
            "izveidots ar citu SKU."
        )

    return (
        "Produkts WooCommerce API datos nav atrasts. "
        "Iespējams, tas ir neatgriezeniski izdzēsts vai "
        "nav atkārtoti importēts."
    )


def main() -> None:
    print("=" * 80)
    print("PAZUDUŠO WOOCOMMERCE SKU DIAGNOSTIKA")
    print("=" * 80)

    print()
    print("Ielādē piegādātāja produktus...")
    supplier_products = supplier.load_products()

    print()
    normal_products = woocommerce.load_products(
        force_refresh=True,
    )

    print()
    trash_products = load_products_by_status(
        status="trash",
    )

    variations = load_all_variations(
        normal_products,
    )

    supplier_map = build_product_map(
        supplier_products,
    )
    normal_map = build_product_map(
        normal_products,
    )
    trash_map = build_product_map(
        trash_products,
    )
    variation_map = build_product_map(
        variations,
    )

    missing_skus = sorted(
        sku
        for sku in supplier_map
        if sku not in normal_map
    )

    all_searchable_products = (
        normal_products
        + trash_products
        + variations
    )

    REPORT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "supplier_sku",
        "supplier_name",
        "supplier_producer",
        "supplier_price",
        "supplier_stock",
        "normal_product_found",
        "normal_product_id",
        "normal_product_status",
        "normal_product_type",
        "trash_product_found",
        "trash_product_id",
        "variation_found",
        "variation_id",
        "variation_parent_id",
        "similar_skus",
        "similar_names",
        "diagnosis",
    ]

    with REPORT_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as report_file:
        writer = csv.DictWriter(
            report_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        total = len(missing_skus)

        for index, sku in enumerate(
            missing_skus,
            start=1,
        ):
            supplier_product = supplier_map[sku]

            normal_product = normal_map.get(sku)
            trash_product = trash_map.get(sku)
            variation = variation_map.get(sku)

            similar_skus = find_similar_products(
                target_value=sku,
                products=all_searchable_products,
                value_getter=product_sku,
                minimum_similarity=MINIMUM_SKU_SIMILARITY,
                limit=SIMILAR_SKU_LIMIT,
            )

            supplier_product_name = normalize_name(
                product_name(supplier_product)
            )

            similar_names = find_similar_products(
                target_value=supplier_product_name,
                products=all_searchable_products,
                value_getter=lambda product: normalize_name(
                    product_name(product)
                ),
                minimum_similarity=MINIMUM_NAME_SIMILARITY,
                limit=SIMILAR_NAME_LIMIT,
            )

            diagnosis = determine_diagnosis(
                normal_product=normal_product,
                trash_product=trash_product,
                variation=variation,
                similar_skus=similar_skus,
                similar_names=similar_names,
            )

            print(
                f"[{index}/{total}] "
                f"{sku} — "
                f"{product_name(supplier_product)}"
            )
            print(f"  {diagnosis}")

            writer.writerow(
                {
                    "supplier_sku": sku,
                    "supplier_name": product_name(
                        supplier_product
                    ),
                    "supplier_producer": normalize_text(
                        supplier_product.get("producer")
                    ),
                    "supplier_price": normalize_text(
                        supplier_product.get("price")
                    ),
                    "supplier_stock": normalize_text(
                        supplier_product.get("stock")
                    ),
                    "normal_product_found": (
                        "Jā"
                        if normal_product is not None
                        else "Nē"
                    ),
                    "normal_product_id": (
                        product_id(normal_product)
                        if normal_product
                        else ""
                    ),
                    "normal_product_status": (
                        product_status(normal_product)
                        if normal_product
                        else ""
                    ),
                    "normal_product_type": (
                        product_type(normal_product)
                        if normal_product
                        else ""
                    ),
                    "trash_product_found": (
                        "Jā"
                        if trash_product is not None
                        else "Nē"
                    ),
                    "trash_product_id": (
                        product_id(trash_product)
                        if trash_product
                        else ""
                    ),
                    "variation_found": (
                        "Jā"
                        if variation is not None
                        else "Nē"
                    ),
                    "variation_id": (
                        product_id(variation)
                        if variation
                        else ""
                    ),
                    "variation_parent_id": (
                        variation.get(
                            "_parent_product_id",
                            "",
                        )
                        if variation
                        else ""
                    ),
                    "similar_skus": format_matches(
                        similar_skus
                    ),
                    "similar_names": format_matches(
                        similar_names
                    ),
                    "diagnosis": diagnosis,
                }
            )

    print()
    print("=" * 80)
    print("DIAGNOSTIKA PABEIGTA")
    print("=" * 80)
    print(
        f"Piegādātāja produkti:          "
        f"{len(supplier_products)}"
    )
    print(
        f"WooCommerce galvenie produkti: "
        f"{len(normal_products)}"
    )
    print(
        f"WooCommerce miskastē:          "
        f"{len(trash_products)}"
    )
    print(
        f"WooCommerce variācijas:        "
        f"{len(variations)}"
    )
    print(
        f"Nav galveno produktu sarakstā: "
        f"{len(missing_skus)}"
    )
    print(f"Atskaite: {REPORT_PATH.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()