from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from src.pricing import calculate_gross_price, prices_are_equal


@dataclass
class ProductChange:
    """
    Viena WooCommerce produkta konstatētās izmaiņas.

    price_new vienmēr ir bruto cena ar PVN.
    stock_new ir piegādātāja noliktavas atlikums.
    """

    sku: str
    name: str
    woo_id: int

    price_old: Decimal | None = None
    price_new: Decimal | None = None

    stock_old: int | None = None
    stock_new: int | None = None

    @property
    def price_changed(self) -> bool:
        """
        Atgriež True, ja WooCommerce un jaunā bruto cena atšķiras.
        """
        if self.price_old is None or self.price_new is None:
            return False

        return not prices_are_equal(
            self.price_old,
            self.price_new,
        )

    @property
    def stock_changed(self) -> bool:
        """
        Atgriež True, ja WooCommerce un piegādātāja atlikumi atšķiras.
        """
        if self.stock_old is None or self.stock_new is None:
            return False

        return self.stock_old != self.stock_new

    @property
    def has_changes(self) -> bool:
        """
        Atgriež True, ja mainījusies cena vai noliktavas atlikums.
        """
        return self.price_changed or self.stock_changed


@dataclass
class ComparisonResult:
    """
    Pilns piegādātāja un WooCommerce produktu salīdzinājuma rezultāts.
    """

    matching_skus: list[str]
    supplier_only_skus: list[str]
    woocommerce_only_skus: list[str]

    duplicate_supplier_skus: list[str]
    duplicate_woocommerce_skus: list[str]

    changes: list[ProductChange]

    @property
    def price_changes(self) -> list[ProductChange]:
        """
        Atgriež tikai produktus, kuriem mainījusies cena.
        """
        return [
            change
            for change in self.changes
            if change.price_changed
        ]

    @property
    def stock_changes(self) -> list[ProductChange]:
        """
        Atgriež tikai produktus, kuriem mainījies atlikums.
        """
        return [
            change
            for change in self.changes
            if change.stock_changed
        ]


def normalize_sku(value: Any) -> str:
    """
    Normalizē SKU salīdzināšanai.
    """
    return str(value or "").strip().upper()


def to_decimal(value: Any) -> Decimal:
    """
    Droši pārvērš vērtību par Decimal.

    Nederīgas vai tukšas vērtības tiek pārvērstas par Decimal("0").
    """
    if isinstance(value, Decimal):
        return value

    text = str(value or "0").strip().replace(",", ".")

    if not text:
        return Decimal("0")

    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def to_int(value: Any) -> int:
    """
    Droši pārvērš vērtību par veselu skaitli.

    Nederīgas vai tukšas vērtības tiek pārvērstas par 0.
    """
    if value in (None, ""):
        return 0

    try:
        return int(
            float(
                str(value).strip().replace(",", ".")
            )
        )
    except (TypeError, ValueError):
        return 0


def build_product_index(
    products: list[dict[str, Any]],
    sku_field: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """
    Izveido produktu indeksu pēc SKU.

    Atgriež:
    - produktu vārdnīcu pēc SKU;
    - dublikātu SKU sarakstu.

    Ja viens SKU atkārtojas vairākas reizes, indeksā tiek saglabāts
    pirmais produkts, bet SKU tiek reģistrēts kā dublikāts.
    """
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


def build_product_change(
    supplier: dict[str, Any],
    woo: dict[str, Any],
    sku: str,
) -> ProductChange:
    """
    Izveido viena produkta izmaiņu objektu.

    Piegādātāja cena tiek uzskatīta par neto cenu un pirms
    salīdzināšanas pārvērsta bruto cenā ar PVN.
    """
    supplier_net_price = to_decimal(
        supplier.get("price")
    )

    supplier_gross_price = calculate_gross_price(
        supplier_net_price
    )

    return ProductChange(
        sku=sku,
        name=str(
            woo.get("name")
            or supplier.get("name")
            or ""
        ),
        woo_id=to_int(
            woo.get("id")
        ),
        price_old=to_decimal(
            woo.get("regular_price")
        ),
        price_new=supplier_gross_price,
        stock_old=to_int(
            woo.get("stock_quantity")
        ),
        stock_new=to_int(
            supplier.get("stock")
        ),
    )


def compare_products(
    supplier_products: list[dict[str, Any]],
    woocommerce_products: list[dict[str, Any]],
) -> ComparisonResult:
    """
    Salīdzina piegādātāja produktus ar WooCommerce produktiem.

    Salīdzināšana notiek pēc normalizēta SKU.

    Cenas:
    - piegādātāja cena tiek uzskatīta par neto;
    - pirms salīdzināšanas tiek aprēķināta bruto cena;
    - WooCommerce regular_price tiek uzskatīta par bruto cenu.

    Atlikumi:
    - piegādātāja stock tiek salīdzināts ar WooCommerce
      stock_quantity.
    """
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

    matching_skus = sorted(
        supplier_skus & woo_skus
    )

    supplier_only_skus = sorted(
        supplier_skus - woo_skus
    )

    woocommerce_only_skus = sorted(
        woo_skus - supplier_skus
    )

    changes: list[ProductChange] = []

    for sku in matching_skus:
        supplier = supplier_index[sku]
        woo = woo_index[sku]

        change = build_product_change(
            supplier=supplier,
            woo=woo,
            sku=sku,
        )

        if change.has_changes:
            changes.append(change)

    return ComparisonResult(
        matching_skus=matching_skus,
        supplier_only_skus=supplier_only_skus,
        woocommerce_only_skus=woocommerce_only_skus,
        duplicate_supplier_skus=supplier_duplicates,
        duplicate_woocommerce_skus=woo_duplicates,
        changes=changes,
    )