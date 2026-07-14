from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass
class ProductChange:
    sku: str
    name: str
    woo_id: int
    price_old: Decimal | None = None
    price_new: Decimal | None = None
    stock_old: int | None = None
    stock_new: int | None = None

    @property
    def price_changed(self) -> bool:
        return (
            self.price_old is not None
            and self.price_new is not None
            and self.price_old != self.price_new
        )

    @property
    def stock_changed(self) -> bool:
        return (
            self.stock_old is not None
            and self.stock_new is not None
            and self.stock_old != self.stock_new
        )


@dataclass
class ComparisonResult:
    matching_skus: list[str]
    supplier_only_skus: list[str]
    woocommerce_only_skus: list[str]
    duplicate_supplier_skus: list[str]
    duplicate_woocommerce_skus: list[str]
    changes: list[ProductChange]


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def to_decimal(value: Any) -> Decimal:
    text = str(value or "0").strip().replace(",", ".")

    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def to_int(value: Any) -> int:
    if value in (None, ""):
        return 0

    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def build_product_index(
    products: list[dict[str, Any]],
    sku_field: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    index: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []

    for product in products:
        sku = normalize_sku(product.get(sku_field))

        if not sku:
            continue

        if sku in index:
            duplicates.append(sku)
            continue

        index[sku] = product

    return index, sorted(set(duplicates))


def compare_products(
    supplier_products: list[dict[str, Any]],
    woocommerce_products: list[dict[str, Any]],
) -> ComparisonResult:
    supplier_index, supplier_duplicates = build_product_index(
        supplier_products,
        "sku",
    )

    woo_index, woo_duplicates = build_product_index(
        woocommerce_products,
        "sku",
    )

    supplier_skus = set(supplier_index)
    woo_skus = set(woo_index)

    matching_skus = sorted(supplier_skus & woo_skus)
    supplier_only_skus = sorted(supplier_skus - woo_skus)
    woocommerce_only_skus = sorted(woo_skus - supplier_skus)

    changes: list[ProductChange] = []

    for sku in matching_skus:
        supplier = supplier_index[sku]
        woo = woo_index[sku]

        change = ProductChange(
            sku=sku,
            name=str(woo.get("name") or supplier.get("name") or ""),
            woo_id=to_int(woo.get("id")),
            price_old=to_decimal(woo.get("regular_price")),
            price_new=to_decimal(supplier.get("price")),
            stock_old=to_int(woo.get("stock_quantity")),
            stock_new=to_int(supplier.get("stock")),
        )

        if change.price_changed or change.stock_changed:
            changes.append(change)

    return ComparisonResult(
        matching_skus=matching_skus,
        supplier_only_skus=supplier_only_skus,
        woocommerce_only_skus=woocommerce_only_skus,
        duplicate_supplier_skus=supplier_duplicates,
        duplicate_woocommerce_skus=woo_duplicates,
        changes=changes,
    )