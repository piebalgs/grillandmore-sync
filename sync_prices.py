from __future__ import annotations

import argparse
import inspect
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from src import supplier
from src import woocommerce
from src.pricing import format_price
from src.sync_engine import ComparisonResult, ProductChange, compare_products


VERSION = "1.0.0"
DEFAULT_BRAND = "WEBER"
SEPARATOR = "=" * 72


@dataclass
class PriceSyncStatistics:
    supplier_loaded: int = 0
    supplier_filtered: int = 0
    woocommerce_loaded: int = 0
    woocommerce_filtered: int = 0

    matching: int = 0
    unchanged: int = 0
    price_changes: int = 0

    updated: int = 0
    failed: int = 0

    supplier_only: int = 0
    woocommerce_only: int = 0

    duplicate_supplier: int = 0
    duplicate_woocommerce: int = 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Salīdzina piegādātāja neto cenas ar WooCommerce bruto cenām "
            "un pēc izvēles atjaunina WooCommerce."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Veikt reālas cenu izmaiņas WooCommerce.",
    )

    parser.add_argument(
        "--brand",
        default=DEFAULT_BRAND,
        help=(
            "Piegādātāja zīmola filtrs. "
            f"Noklusējums: {DEFAULT_BRAND}. "
            "Lai neizmantotu zīmola filtru, norādi --brand ALL."
        ),
    )

    parser.add_argument(
        "--sku",
        help="Apstrādāt tikai vienu konkrētu SKU.",
    )

    parser.add_argument(
        "--show-unchanged",
        action="store_true",
        help="Parādīt arī produktus, kuru cena nemainās.",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="APPLY režīmā neprasīt papildu apstiprinājumu.",
    )

    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_sku(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_brand(value: Any) -> str:
    return normalize_text(value).upper()


def resolve_callable(
    module: Any,
    possible_names: tuple[str, ...],
    description: str,
) -> Callable[..., Any]:
    for name in possible_names:
        candidate = getattr(module, name, None)

        if callable(candidate):
            return candidate

    available = sorted(
        name
        for name in dir(module)
        if not name.startswith("_")
    )

    raise RuntimeError(
        f"Modulī {module.__name__} neatradu funkciju: {description}.\n"
        f"Meklētie nosaukumi: {', '.join(possible_names)}\n"
        f"Pieejamie publiskie nosaukumi: {', '.join(available)}"
    )


def load_supplier_products() -> list[dict[str, Any]]:
    loader = resolve_callable(
        supplier,
        (
            "load_products",
            "load_supplier_products",
            "get_products",
        ),
        "piegādātāja produktu ielādei",
    )

    products = loader()

    if products is None:
        return []

    if not isinstance(products, list):
        products = list(products)

    return products


def load_woocommerce_products() -> list[dict[str, Any]]:
    loader = resolve_callable(
        woocommerce,
        (
            "load_products",
            "load_woocommerce_products",
            "get_products",
        ),
        "WooCommerce produktu ielādei",
    )

    products = loader()

    if products is None:
        return []

    if not isinstance(products, list):
        products = list(products)

    return products


def supplier_brand(product: dict[str, Any]) -> str:
    return normalize_brand(
        product.get("producer")
        or product.get("brand")
        or product.get("manufacturer")
    )


def filter_supplier_products(
    products: list[dict[str, Any]],
    brand: str | None,
    sku: str | None,
) -> list[dict[str, Any]]:
    normalized_brand = normalize_brand(brand)
    normalized_sku = normalize_sku(sku)

    use_brand_filter = bool(
        normalized_brand
        and normalized_brand not in {"ALL", "*", "VISI"}
    )

    filtered: list[dict[str, Any]] = []

    for product in products:
        product_sku = normalize_sku(product.get("sku"))

        if normalized_sku and product_sku != normalized_sku:
            continue

        if use_brand_filter:
            product_brand = supplier_brand(product)

            if normalized_brand not in product_brand:
                continue

        filtered.append(product)

    return filtered


def filter_woocommerce_products(
    products: list[dict[str, Any]],
    supplier_products: list[dict[str, Any]],
    sku: str | None,
) -> list[dict[str, Any]]:
    normalized_sku = normalize_sku(sku)

    supplier_skus = {
        normalize_sku(product.get("sku"))
        for product in supplier_products
        if normalize_sku(product.get("sku"))
    }

    filtered: list[dict[str, Any]] = []

    for product in products:
        product_sku = normalize_sku(product.get("sku"))

        if not product_sku:
            continue

        if normalized_sku:
            if product_sku == normalized_sku:
                filtered.append(product)

            continue

        if product_sku in supplier_skus:
            filtered.append(product)

    return filtered


def format_euro(value: Decimal | None) -> str:
    if value is None:
        return "nav"

    return f"{format_price(value)} €"


def format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    minutes, seconds_left = divmod(rounded, 60)
    hours, minutes_left = divmod(minutes, 60)

    if hours:
        return f"{hours:02d}:{minutes_left:02d}:{seconds_left:02d}"

    return f"{minutes_left:02d}:{seconds_left:02d}"


def print_header(
    apply_changes: bool,
    brand: str,
    sku: str | None,
) -> None:
    mode = "APPLY" if apply_changes else "DRY RUN"

    normalized_brand = normalize_text(brand)

    if normalize_brand(normalized_brand) in {"ALL", "*", "VISI"}:
        normalized_brand = "visi zīmoli"

    print(SEPARATOR)
    print("WooCommerce cenu sinhronizācija")
    print(SEPARATOR)
    print(f"Versija:            {VERSION}")
    print(f"Režīms:             {mode}")
    print(f"Zīmola filtrs:      {normalized_brand or 'nav'}")
    print(f"SKU filtrs:         {normalize_text(sku) or 'nav'}")
    print(SEPARATOR)


def print_price_change(
    change: ProductChange,
    index: int,
    total: int,
    apply_mode: bool,
) -> None:
    action = "ATJAUNINĀT" if apply_mode else "MAINĪT"

    print(
        f"[{index}/{total}] {action} "
        f"SKU {change.sku}"
    )
    print(f"  Produkts:         {change.name or 'bez nosaukuma'}")
    print(f"  WooCommerce cena: {format_euro(change.price_old)}")
    print(f"  Jaunā bruto cena: {format_euro(change.price_new)}")


def print_unchanged_products(
    result: ComparisonResult,
    supplier_products: list[dict[str, Any]],
    woocommerce_products: list[dict[str, Any]],
) -> None:
    changed_skus = {
        change.sku
        for change in result.price_changes
    }

    supplier_by_sku = {
        normalize_sku(product.get("sku")): product
        for product in supplier_products
        if normalize_sku(product.get("sku"))
    }

    woo_by_sku = {
        normalize_sku(product.get("sku")): product
        for product in woocommerce_products
        if normalize_sku(product.get("sku"))
    }

    unchanged_skus = [
        sku
        for sku in result.matching_skus
        if sku not in changed_skus
    ]

    if not unchanged_skus:
        return

    print()
    print("Produkti bez cenu izmaiņām")
    print("-" * 72)

    for sku in unchanged_skus:
        supplier_product = supplier_by_sku.get(sku, {})
        woo_product = woo_by_sku.get(sku, {})

        name = (
            normalize_text(woo_product.get("name"))
            or normalize_text(supplier_product.get("name"))
            or "bez nosaukuma"
        )

        price = normalize_text(woo_product.get("regular_price")) or "0.00"

        print(f"✓ {sku} | {price} € | {name}")


def confirm_apply(
    changes: list[ProductChange],
    skip_confirmation: bool,
) -> bool:
    if skip_confirmation:
        return True

    print()
    print(SEPARATOR)
    print(
        f"UZMANĪBU: WooCommerce tiks atjauninātas "
        f"{len(changes)} produktu cenas."
    )
    print("Lai turpinātu, ieraksti: APPLY")
    print(SEPARATOR)

    answer = input("> ").strip()

    return answer == "APPLY"


def call_price_update(
    product_id: int,
    new_price: Decimal,
) -> Any:
    updater = resolve_callable(
        woocommerce,
        (
            "update_product_price",
            "set_product_price",
        ),
        "WooCommerce produkta cenas atjaunināšanai",
    )

    price_text = format_price(new_price)

    signature = inspect.signature(updater)
    parameter_names = list(signature.parameters)

    keyword_arguments: dict[str, Any] = {}

    id_parameter_names = (
        "product_id",
        "woo_id",
        "woocommerce_id",
        "id",
    )

    price_parameter_names = (
        "price",
        "new_price",
        "regular_price",
        "gross_price",
    )

    for parameter_name in id_parameter_names:
        if parameter_name in parameter_names:
            keyword_arguments[parameter_name] = product_id
            break

    for parameter_name in price_parameter_names:
        if parameter_name in parameter_names:
            keyword_arguments[parameter_name] = price_text
            break

    if len(keyword_arguments) == 2:
        return updater(**keyword_arguments)

    return updater(product_id, price_text)


def apply_price_changes(
    changes: list[ProductChange],
    statistics: PriceSyncStatistics,
) -> None:
    total = len(changes)

    for index, change in enumerate(changes, start=1):
        print()
        print_price_change(
            change=change,
            index=index,
            total=total,
            apply_mode=True,
        )

        if change.price_new is None:
            statistics.failed += 1
            print("  Rezultāts:        KĻŪDA — jaunā cena nav pieejama")
            continue

        if change.woo_id <= 0:
            statistics.failed += 1
            print("  Rezultāts:        KĻŪDA — nav WooCommerce produkta ID")
            continue

        try:
            call_price_update(
                product_id=change.woo_id,
                new_price=change.price_new,
            )

            statistics.updated += 1
            print("  Rezultāts:        ATJAUNINĀTS")

        except Exception as exc:
            statistics.failed += 1
            print(f"  Rezultāts:        KĻŪDA — {exc}")


def print_dry_run_changes(
    changes: list[ProductChange],
) -> None:
    total = len(changes)

    for index, change in enumerate(changes, start=1):
        print()
        print_price_change(
            change=change,
            index=index,
            total=total,
            apply_mode=False,
        )
        print("  Rezultāts:        DRY RUN — izmaiņas nav veiktas")


def build_statistics(
    supplier_loaded: list[dict[str, Any]],
    supplier_filtered: list[dict[str, Any]],
    woocommerce_loaded: list[dict[str, Any]],
    woocommerce_filtered: list[dict[str, Any]],
    result: ComparisonResult,
) -> PriceSyncStatistics:
    price_change_count = len(result.price_changes)

    return PriceSyncStatistics(
        supplier_loaded=len(supplier_loaded),
        supplier_filtered=len(supplier_filtered),
        woocommerce_loaded=len(woocommerce_loaded),
        woocommerce_filtered=len(woocommerce_filtered),
        matching=len(result.matching_skus),
        unchanged=max(
            0,
            len(result.matching_skus) - price_change_count,
        ),
        price_changes=price_change_count,
        supplier_only=len(result.supplier_only_skus),
        woocommerce_only=len(result.woocommerce_only_skus),
        duplicate_supplier=len(result.duplicate_supplier_skus),
        duplicate_woocommerce=len(
            result.duplicate_woocommerce_skus
        ),
    )


def print_missing_skus(result: ComparisonResult) -> None:
    if result.supplier_only_skus:
        print()
        print("Piegādātāja SKU, kas nav atrasti WooCommerce")
        print("-" * 72)

        for sku in result.supplier_only_skus:
            print(f"- {sku}")

    if result.woocommerce_only_skus:
        print()
        print("WooCommerce SKU, kas nav atrasti piegādātāja datos")
        print("-" * 72)

        for sku in result.woocommerce_only_skus:
            print(f"- {sku}")


def print_duplicates(result: ComparisonResult) -> None:
    if result.duplicate_supplier_skus:
        print()
        print("Dublikāti piegādātāja datos")
        print("-" * 72)

        for sku in result.duplicate_supplier_skus:
            print(f"- {sku}")

    if result.duplicate_woocommerce_skus:
        print()
        print("Dublikāti WooCommerce")
        print("-" * 72)

        for sku in result.duplicate_woocommerce_skus:
            print(f"- {sku}")


def print_summary(
    statistics: PriceSyncStatistics,
    apply_changes: bool,
    elapsed_seconds: float,
) -> None:
    mode = "APPLY" if apply_changes else "DRY RUN"

    print()
    print(SEPARATOR)
    print("Kopsavilkums")
    print(SEPARATOR)
    print(f"Režīms:                     {mode}")
    print(f"Piegādātāja produkti:       {statistics.supplier_loaded}")
    print(f"Pēc piegādātāja filtra:     {statistics.supplier_filtered}")
    print(f"WooCommerce produkti:       {statistics.woocommerce_loaded}")
    print(f"Pēc WooCommerce filtra:     {statistics.woocommerce_filtered}")
    print(f"Sakrītošie SKU:             {statistics.matching}")
    print(f"Cenas jāmaina:              {statistics.price_changes}")
    print(f"Cenas bez izmaiņām:         {statistics.unchanged}")
    print(f"Atjaunināti:                {statistics.updated}")
    print(f"Kļūdas:                     {statistics.failed}")
    print(f"Tikai piegādātāja datos:    {statistics.supplier_only}")
    print(f"Tikai WooCommerce datos:    {statistics.woocommerce_only}")
    print(f"Piegādātāja dublikāti:      {statistics.duplicate_supplier}")
    print(
        f"WooCommerce dublikāti:      "
        f"{statistics.duplicate_woocommerce}"
    )
    print(f"Izpildes laiks:             {format_duration(elapsed_seconds)}")
    print(SEPARATOR)

    if not apply_changes and statistics.price_changes:
        print(
            "DRY RUN pabeigts. Lai veiktu izmaiņas, palaid skriptu "
            "ar parametru --apply."
        )


def main() -> int:
    arguments = parse_arguments()
    started_at = time.monotonic()

    print_header(
        apply_changes=arguments.apply,
        brand=arguments.brand,
        sku=arguments.sku,
    )

    try:
        print("Lejupielādē piegādātāja produktus...")
        supplier_loaded = load_supplier_products()
        print(f"Piegādātāja produkti ielādēti: {len(supplier_loaded)}")

        supplier_filtered = filter_supplier_products(
            products=supplier_loaded,
            brand=arguments.brand,
            sku=arguments.sku,
        )
        print(
            f"Pēc piegādātāja filtra: "
            f"{len(supplier_filtered)}"
        )

        if not supplier_filtered:
            print()
            print("Nav atrasts neviens filtram atbilstošs piegādātāja produkts.")
            return 1

        print()
        print("Ielādē WooCommerce produktus...")
        woocommerce_loaded = load_woocommerce_products()
        print(f"WooCommerce produkti ielādēti: {len(woocommerce_loaded)}")

        woocommerce_filtered = filter_woocommerce_products(
            products=woocommerce_loaded,
            supplier_products=supplier_filtered,
            sku=arguments.sku,
        )
        print(
            f"Pēc WooCommerce filtra: "
            f"{len(woocommerce_filtered)}"
        )

        print()
        print("Salīdzina cenas...")

        result = compare_products(
            supplier_products=supplier_filtered,
            woocommerce_products=woocommerce_filtered,
        )

        statistics = build_statistics(
            supplier_loaded=supplier_loaded,
            supplier_filtered=supplier_filtered,
            woocommerce_loaded=woocommerce_loaded,
            woocommerce_filtered=woocommerce_filtered,
            result=result,
        )

        price_changes = result.price_changes

        print(f"Sakrītošie SKU: {statistics.matching}")
        print(f"Cenas jāmaina:  {statistics.price_changes}")
        print(f"Bez izmaiņām:   {statistics.unchanged}")

        print_duplicates(result)
        print_missing_skus(result)

        if arguments.show_unchanged:
            print_unchanged_products(
                result=result,
                supplier_products=supplier_filtered,
                woocommerce_products=woocommerce_filtered,
            )

        if not price_changes:
            elapsed = time.monotonic() - started_at

            print()
            print("Neviena cena nav jāmaina.")

            print_summary(
                statistics=statistics,
                apply_changes=arguments.apply,
                elapsed_seconds=elapsed,
            )

            return 0

        if arguments.apply:
            if not confirm_apply(
                changes=price_changes,
                skip_confirmation=arguments.yes,
            ):
                print()
                print("Darbība atcelta. WooCommerce izmaiņas nav veiktas.")
                return 0

            apply_price_changes(
                changes=price_changes,
                statistics=statistics,
            )

        else:
            print_dry_run_changes(price_changes)

        elapsed = time.monotonic() - started_at

        print_summary(
            statistics=statistics,
            apply_changes=arguments.apply,
            elapsed_seconds=elapsed,
        )

        return 1 if statistics.failed else 0

    except KeyboardInterrupt:
        print()
        print("Darbību pārtrauca lietotājs.")
        return 130

    except Exception as exc:
        elapsed = time.monotonic() - started_at

        print()
        print(SEPARATOR)
        print("KRITISKA KĻŪDA")
        print(SEPARATOR)
        print(str(exc))
        print(f"Izpildes laiks: {format_duration(elapsed)}")
        print(SEPARATOR)

        return 1


if __name__ == "__main__":
    sys.exit(main())