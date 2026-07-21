from __future__ import annotations

import sys
from decimal import Decimal
from typing import Any, Callable

from src import supplier, woocommerce
from src.pricing import format_price
from src.sync_common import SyncRunnerConfig, exit_with_sync_result, normalize_sku
from src.sync_engine import ComparisonResult, ProductChange, compare_products


def resolve_callable(
    module: Any,
    possible_names: tuple[str, ...],
    description: str,
) -> Callable[..., Any]:
    """
    Atrod modulī pirmo pieejamo funkciju no norādītajiem nosaukumiem.

    Tas ļauj saglabāt savietojamību, ja produktu ielādes funkcijas
    nosaukums dažādās projekta versijās nedaudz atšķiras.
    """
    for name in possible_names:
        candidate = getattr(module, name, None)

        if callable(candidate):
            return candidate

    searched_names = ", ".join(possible_names)

    raise RuntimeError(
        f"Modulī {module.__name__} neatradu funkciju: {description}. "
        f"Meklētie nosaukumi: {searched_names}."
    )


def load_supplier_products() -> list[dict[str, Any]]:
    """
    Ielādē visus piegādātāja produktus.
    """
    loader = resolve_callable(
        module=supplier,
        possible_names=(
            "load_products",
            "load_supplier_products",
            "get_products",
        ),
        description="piegādātāja produktu ielādei",
    )

    products = loader()

    if products is None:
        return []

    return list(products)


def load_woocommerce_products() -> list[dict[str, Any]]:
    """
    Ielādē visus WooCommerce produktus.
    """
    loader = resolve_callable(
        module=woocommerce,
        possible_names=(
            "load_products",
            "load_woocommerce_products",
            "get_products",
        ),
        description="WooCommerce produktu ielādei",
    )

    products = loader()

    if products is None:
        return []

    return list(products)


def select_price_changes(
    result: ComparisonResult,
) -> list[ProductChange]:
    """
    No pilnā salīdzinājuma rezultāta atlasa tikai cenu izmaiņas.
    """
    return result.price_changes


def format_euro(value: Decimal | None) -> str:
    """
    Noformē cenu attēlošanai terminālī.
    """
    if value is None:
        return "nav"

    return f"{format_price(value)} €"


def print_price_change(
    change: ProductChange,
    index: int,
    total: int,
    apply_mode: bool,
) -> None:
    """
    Parāda vienas cenas izmaiņas informāciju.
    """
    action = "ATJAUNINĀT" if apply_mode else "MAINĪT"

    print()
    print(f"[{index}/{total}] {action} SKU {change.sku}")
    print(f"  Produkts:         {change.name or 'bez nosaukuma'}")
    print(f"  WooCommerce cena: {format_euro(change.price_old)}")
    print(f"  Jaunā bruto cena: {format_euro(change.price_new)}")


def update_price(change: ProductChange) -> dict[str, Any]:
    """
    Atjaunina viena WooCommerce produkta regular_price.
    """
    if change.woo_id <= 0:
        raise ValueError(
            f"SKU {change.sku}: nav derīga WooCommerce produkta ID."
        )

    if change.price_new is None:
        raise ValueError(
            f"SKU {change.sku}: jaunā bruto cena nav pieejama."
        )

    return woocommerce.update_product_price(
        product_id=change.woo_id,
        gross_price=change.price_new,
    )


def print_unchanged_products(
    result: ComparisonResult,
    supplier_products: list[dict[str, Any]],
    woocommerce_products: list[dict[str, Any]],
) -> None:
    """
    Parāda produktus, kuru WooCommerce cena jau ir pareiza.
    """
    changed_skus = {
        normalize_sku(change.sku)
        for change in result.price_changes
    }

    supplier_by_sku = {
        normalize_sku(product.get("sku")): product
        for product in supplier_products
        if normalize_sku(product.get("sku"))
    }

    woocommerce_by_sku = {
        normalize_sku(product.get("sku")): product
        for product in woocommerce_products
        if normalize_sku(product.get("sku"))
    }

    unchanged_skus = [
        normalize_sku(sku)
        for sku in result.matching_skus
        if normalize_sku(sku) not in changed_skus
    ]

    if not unchanged_skus:
        return

    print()
    print("Produkti bez cenu izmaiņām")
    print("-" * 72)

    for sku in unchanged_skus:
        supplier_product = supplier_by_sku.get(sku, {})
        woocommerce_product = woocommerce_by_sku.get(sku, {})

        name = str(
            woocommerce_product.get("name")
            or supplier_product.get("name")
            or "bez nosaukuma"
        ).strip()

        regular_price = str(
            woocommerce_product.get("regular_price")
            or "0.00"
        ).strip()

        print(f"✓ {sku} | {regular_price} € | {name}")


def build_config() -> SyncRunnerConfig:
    """
    Izveido cenu sinhronizācijas konfigurāciju SyncRunner frameworkam.
    """
    return SyncRunnerConfig(
        name="WooCommerce cenu sinhronizācija",
        description=(
            "Salīdzina piegādātāja neto cenas ar WooCommerce bruto "
            "cenām un pēc izvēles atjaunina WooCommerce."
        ),
        change_label="Cenas jāmaina",
        supplier_loader=load_supplier_products,
        woocommerce_loader=load_woocommerce_products,
        comparator=compare_products,
        change_selector=select_price_changes,
        change_printer=print_price_change,
        updater=update_price,
        unchanged_printer=print_unchanged_products,
        require_confirmation=True,
        show_missing_skus=True,
        show_duplicates=True,
    )


def main() -> None:
    """
    Palaiž cenu sinhronizāciju.
    """
    exit_with_sync_result(
        config=build_config(),
    )


if __name__ == "__main__":
    main()