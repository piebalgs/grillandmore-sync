from __future__ import annotations

import sys
from typing import Any

from src import woocommerce
from src.product_loaders import (
    load_supplier_products,
    load_woocommerce_products,
)
from src.sync_common import (
    SyncRunnerConfig,
    normalize_sku,
    run_sync,
)
from src.sync_engine import (
    ComparisonResult,
    ProductChange,
    compare_products,
)


def select_stock_changes(
    result: ComparisonResult,
) -> list[ProductChange]:
    """
    No pilnā produktu salīdzinājuma atlasa tikai atlikumu izmaiņas.
    """
    return result.stock_changes


def format_stock(value: int | None) -> str:
    """
    Noformē noliktavas atlikumu termināļa izvadei.
    """
    if value is None:
        return "nav"

    return str(value)


def print_stock_change(
    change: ProductChange,
    index: int,
    total: int,
    apply_mode: bool,
) -> None:
    """
    Parāda viena produkta atlikuma izmaiņas informāciju.
    """
    action = "ATJAUNINĀT" if apply_mode else "MAINĪT"

    print()
    print(f"[{index}/{total}] {action} SKU {change.sku}")
    print(
        f"  Produkts:              "
        f"{change.name or 'bez nosaukuma'}"
    )
    print(
        "  WooCommerce atlikums: "
        f"{format_stock(change.stock_old)}"
    )
    print(
        "  Piegādātāja atlikums: "
        f"{format_stock(change.stock_new)}"
    )


def update_stock(change: ProductChange) -> dict[str, Any]:
    """
    Atjaunina viena WooCommerce produkta noliktavas atlikumu.
    """
    if change.woo_id <= 0:
        raise ValueError(
            f"SKU {change.sku}: nav derīga WooCommerce produkta ID."
        )

    if change.stock_new is None:
        raise ValueError(
            f"SKU {change.sku}: jaunais noliktavas atlikums "
            "nav pieejams."
        )

    return woocommerce.update_product_stock(
        product_id=change.woo_id,
        stock_quantity=change.stock_new,
    )


def print_unchanged_products(
    result: ComparisonResult,
    supplier_products: list[dict[str, Any]],
    woocommerce_products: list[dict[str, Any]],
) -> None:
    """
    Parāda produktus, kuru WooCommerce atlikums jau sakrīt ar
    piegādātāja norādīto atlikumu.
    """
    changed_skus = {
        normalize_sku(change.sku)
        for change in result.stock_changes
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
    print("Produkti bez atlikuma izmaiņām")
    print("-" * 72)

    for sku in unchanged_skus:
        supplier_product = supplier_by_sku.get(sku, {})
        woocommerce_product = woocommerce_by_sku.get(sku, {})

        name = str(
            woocommerce_product.get("name")
            or supplier_product.get("name")
            or "bez nosaukuma"
        ).strip()

        stock_quantity = woocommerce_product.get(
            "stock_quantity"
        )

        if stock_quantity is None:
            stock_quantity = 0

        print(
            f"✓ {sku} | atlikums {stock_quantity} | {name}"
        )


def build_config() -> SyncRunnerConfig:
    """
    Izveido atlikumu sinhronizācijas konfigurāciju.
    """
    return SyncRunnerConfig(
        name="WooCommerce atlikumu sinhronizācija",
        description=(
            "Salīdzina piegādātāja noliktavas atlikumus ar "
            "WooCommerce atlikumiem un pēc izvēles atjaunina "
            "WooCommerce produktus."
        ),
        change_label="Atlikumi jāmaina",
        supplier_loader=load_supplier_products,
        woocommerce_loader=load_woocommerce_products,
        comparator=compare_products,
        change_selector=select_stock_changes,
        change_printer=print_stock_change,
        updater=update_stock,
        unchanged_printer=print_unchanged_products,
        require_confirmation=True,
        show_missing_skus=True,
        show_duplicates=True,
    )


def run() -> int:
    """
    Palaiž atlikumu sinhronizāciju un atgriež rezultāta kodu.

    0 — sinhronizācija pabeigta bez kļūdām.
    1 — sinhronizācijas laikā radās kļūda.
    130 — darbību pārtrauca lietotājs.
    """
    return run_sync(
        config=build_config(),
    )


def main() -> None:
    """
    Palaiž atlikumu sinhronizāciju kā termināļa komandu.
    """
    sys.exit(run())


if __name__ == "__main__":
    main()