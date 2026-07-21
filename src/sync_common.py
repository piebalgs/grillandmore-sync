from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from config import (
    DEFAULT_BRAND,
    DEFAULT_DRY_RUN,
    PROJECT_NAME,
    PROJECT_VERSION,
    SEPARATOR,
    SUBSEPARATOR,
    SYMBOL_ERROR,
    SYMBOL_OK,
    SYMBOL_WARNING,
)


Product = dict[str, Any]
ProductLoader = Callable[[], Iterable[Product]]
Comparator = Callable[[list[Product], list[Product]], Any]
ChangeUpdater = Callable[[Any], Any]
ChangePrinter = Callable[[Any, int, int, bool], None]
ChangeSelector = Callable[[Any], Sequence[Any]]


@dataclass
class SyncArguments:
    apply: bool
    brand: str
    sku: str | None
    show_unchanged: bool
    assume_yes: bool

    @property
    def dry_run(self) -> bool:
        return not self.apply


@dataclass
class SyncStatistics:
    supplier_loaded: int = 0
    supplier_filtered: int = 0
    woocommerce_loaded: int = 0
    woocommerce_filtered: int = 0

    matching: int = 0
    changes: int = 0
    unchanged: int = 0

    updated: int = 0
    failed: int = 0
    skipped: int = 0

    supplier_only: int = 0
    woocommerce_only: int = 0

    duplicate_supplier: int = 0
    duplicate_woocommerce: int = 0

    elapsed_seconds: float = 0.0

    errors: list[str] = field(default_factory=list)


@dataclass
class SyncRunnerConfig:
    name: str
    change_label: str

    supplier_loader: ProductLoader
    woocommerce_loader: ProductLoader
    comparator: Comparator
    change_selector: ChangeSelector
    updater: ChangeUpdater
    change_printer: ChangePrinter

    default_brand: str = DEFAULT_BRAND

    description: str | None = None
    require_confirmation: bool = True
    show_missing_skus: bool = True
    show_duplicates: bool = True


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_sku(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_brand(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_integer(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return int(value)

    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return default


def ensure_product_list(products: Iterable[Product] | None) -> list[Product]:
    if products is None:
        return []

    if isinstance(products, list):
        return products

    return list(products)


def product_sku(product: Product) -> str:
    return normalize_sku(
        product.get("sku")
        or product.get("catalogue_number")
        or product.get("catalog_number")
    )


def product_name(product: Product) -> str:
    return normalize_text(
        product.get("name")
        or product.get("title")
        or product.get("product_name")
    )


def product_brand(product: Product) -> str:
    return normalize_brand(
        product.get("producer")
        or product.get("brand")
        or product.get("manufacturer")
    )


def should_filter_brand(brand: str | None) -> bool:
    normalized = normalize_brand(brand)

    return bool(
        normalized
        and normalized not in {"ALL", "*", "VISI", "VISI ZĪMOLI"}
    )


def filter_supplier_products(
    products: Iterable[Product],
    brand: str | None = None,
    sku: str | None = None,
) -> list[Product]:
    normalized_brand = normalize_brand(brand)
    normalized_sku = normalize_sku(sku)

    filtered: list[Product] = []

    for product in products:
        current_sku = product_sku(product)

        if normalized_sku and current_sku != normalized_sku:
            continue

        if should_filter_brand(normalized_brand):
            current_brand = product_brand(product)

            if normalized_brand not in current_brand:
                continue

        filtered.append(product)

    return filtered


def filter_woocommerce_products(
    products: Iterable[Product],
    supplier_products: Iterable[Product],
    sku: str | None = None,
) -> list[Product]:
    normalized_sku = normalize_sku(sku)

    supplier_skus = {
        product_sku(product)
        for product in supplier_products
        if product_sku(product)
    }

    filtered: list[Product] = []

    for product in products:
        current_sku = product_sku(product)

        if not current_sku:
            continue

        if normalized_sku:
            if current_sku == normalized_sku:
                filtered.append(product)

            continue

        if current_sku in supplier_skus:
            filtered.append(product)

    return filtered


def build_argument_parser(
    name: str,
    description: str | None = None,
    default_brand: str = DEFAULT_BRAND,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=name,
        description=description,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        default=not DEFAULT_DRY_RUN,
        help="Veikt reālas izmaiņas WooCommerce.",
    )

    parser.add_argument(
        "--brand",
        default=default_brand,
        help=(
            f"Piegādātāja zīmola filtrs. Noklusējums: {default_brand}. "
            "Lai apstrādātu visus zīmolus, izmanto --brand ALL."
        ),
    )

    parser.add_argument(
        "--sku",
        help="Apstrādāt tikai vienu konkrētu SKU.",
    )

    parser.add_argument(
        "--show-unchanged",
        action="store_true",
        help="Parādīt arī produktus bez izmaiņām.",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="APPLY režīmā neprasīt papildu apstiprinājumu.",
    )

    return parser


def parse_sync_arguments(
    name: str,
    description: str | None = None,
    default_brand: str = DEFAULT_BRAND,
) -> SyncArguments:
    parser = build_argument_parser(
        name=name,
        description=description,
        default_brand=default_brand,
    )

    namespace = parser.parse_args()

    return SyncArguments(
        apply=bool(namespace.apply),
        brand=normalize_text(namespace.brand),
        sku=normalize_text(namespace.sku) or None,
        show_unchanged=bool(namespace.show_unchanged),
        assume_yes=bool(namespace.yes),
    )


def format_duration(seconds: float) -> str:
    rounded_seconds = max(0, int(round(seconds)))

    minutes, remaining_seconds = divmod(rounded_seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)

    if hours:
        return (
            f"{hours:02d}:"
            f"{remaining_minutes:02d}:"
            f"{remaining_seconds:02d}"
        )

    return f"{remaining_minutes:02d}:{remaining_seconds:02d}"


def print_header(
    name: str,
    arguments: SyncArguments,
) -> None:
    mode = "APPLY" if arguments.apply else "DRY RUN"

    brand = arguments.brand or "nav"

    if not should_filter_brand(brand):
        brand = "visi zīmoli"

    print(SEPARATOR)
    print(name)
    print(SEPARATOR)
    print(f"Projekts:            {PROJECT_NAME}")
    print(f"Versija:             {PROJECT_VERSION}")
    print(f"Režīms:              {mode}")
    print(f"Zīmola filtrs:       {brand}")
    print(f"SKU filtrs:          {arguments.sku or 'nav'}")
    print(SEPARATOR)


def print_section(title: str) -> None:
    print()
    print(title)
    print(SUBSEPARATOR)


def confirm_apply(
    item_count: int,
    item_label: str,
    assume_yes: bool = False,
) -> bool:
    if assume_yes:
        return True

    print()
    print(SEPARATOR)
    print(
        f"{SYMBOL_WARNING} UZMANĪBU: WooCommerce tiks veiktas "
        f"{item_count} {item_label}."
    )
    print("Lai turpinātu, ieraksti: APPLY")
    print(SEPARATOR)

    try:
        answer = input("> ").strip()
    except EOFError:
        return False

    return answer == "APPLY"


def get_result_sequence(
    result: Any,
    *attribute_names: str,
) -> list[Any]:
    for attribute_name in attribute_names:
        value = getattr(result, attribute_name, None)

        if value is not None:
            return list(value)

    return []


def get_matching_skus(result: Any) -> list[str]:
    return [
        normalize_sku(value)
        for value in get_result_sequence(
            result,
            "matching_skus",
            "matched_skus",
        )
        if normalize_sku(value)
    ]


def get_supplier_only_skus(result: Any) -> list[str]:
    return [
        normalize_sku(value)
        for value in get_result_sequence(
            result,
            "supplier_only_skus",
            "missing_in_woocommerce",
        )
        if normalize_sku(value)
    ]


def get_woocommerce_only_skus(result: Any) -> list[str]:
    return [
        normalize_sku(value)
        for value in get_result_sequence(
            result,
            "woocommerce_only_skus",
            "missing_in_supplier",
        )
        if normalize_sku(value)
    ]


def get_duplicate_supplier_skus(result: Any) -> list[str]:
    return [
        normalize_sku(value)
        for value in get_result_sequence(
            result,
            "duplicate_supplier_skus",
            "supplier_duplicates",
        )
        if normalize_sku(value)
    ]


def get_duplicate_woocommerce_skus(result: Any) -> list[str]:
    return [
        normalize_sku(value)
        for value in get_result_sequence(
            result,
            "duplicate_woocommerce_skus",
            "woocommerce_duplicates",
        )
        if normalize_sku(value)
    ]


def build_statistics(
    supplier_loaded: Sequence[Product],
    supplier_filtered: Sequence[Product],
    woocommerce_loaded: Sequence[Product],
    woocommerce_filtered: Sequence[Product],
    result: Any,
    changes: Sequence[Any],
) -> SyncStatistics:
    matching_skus = get_matching_skus(result)
    supplier_only_skus = get_supplier_only_skus(result)
    woocommerce_only_skus = get_woocommerce_only_skus(result)
    duplicate_supplier_skus = get_duplicate_supplier_skus(result)
    duplicate_woocommerce_skus = get_duplicate_woocommerce_skus(result)

    return SyncStatistics(
        supplier_loaded=len(supplier_loaded),
        supplier_filtered=len(supplier_filtered),
        woocommerce_loaded=len(woocommerce_loaded),
        woocommerce_filtered=len(woocommerce_filtered),
        matching=len(matching_skus),
        changes=len(changes),
        unchanged=max(0, len(matching_skus) - len(changes)),
        supplier_only=len(supplier_only_skus),
        woocommerce_only=len(woocommerce_only_skus),
        duplicate_supplier=len(duplicate_supplier_skus),
        duplicate_woocommerce=len(duplicate_woocommerce_skus),
    )


def print_sku_list(
    title: str,
    skus: Sequence[str],
) -> None:
    if not skus:
        return

    print_section(title)

    for sku in skus:
        print(f"- {sku}")


def print_result_details(
    result: Any,
    show_missing_skus: bool,
    show_duplicates: bool,
) -> None:
    if show_duplicates:
        print_sku_list(
            title="Dublikāti piegādātāja datos",
            skus=get_duplicate_supplier_skus(result),
        )

        print_sku_list(
            title="Dublikāti WooCommerce",
            skus=get_duplicate_woocommerce_skus(result),
        )

    if show_missing_skus:
        print_sku_list(
            title="Piegādātāja SKU, kas nav atrasti WooCommerce",
            skus=get_supplier_only_skus(result),
        )

        print_sku_list(
            title="WooCommerce SKU, kas nav atrasti piegādātāja datos",
            skus=get_woocommerce_only_skus(result),
        )


def print_summary(
    statistics: SyncStatistics,
    arguments: SyncArguments,
    change_label: str,
) -> None:
    mode = "APPLY" if arguments.apply else "DRY RUN"

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
    print(f"{change_label}:             {statistics.changes}")
    print(f"Bez izmaiņām:               {statistics.unchanged}")
    print(f"Atjaunināti:                {statistics.updated}")
    print(f"Izlaisti:                   {statistics.skipped}")
    print(f"Kļūdas:                     {statistics.failed}")
    print(f"Tikai piegādātāja datos:    {statistics.supplier_only}")
    print(f"Tikai WooCommerce datos:    {statistics.woocommerce_only}")
    print(f"Piegādātāja dublikāti:      {statistics.duplicate_supplier}")
    print(
        f"WooCommerce dublikāti:      "
        f"{statistics.duplicate_woocommerce}"
    )
    print(
        f"Izpildes laiks:             "
        f"{format_duration(statistics.elapsed_seconds)}"
    )
    print(SEPARATOR)

    if statistics.errors:
        print()
        print(f"{SYMBOL_ERROR} Kļūdu apraksti")
        print(SUBSEPARATOR)

        for error in statistics.errors:
            print(f"- {error}")

    if arguments.dry_run and statistics.changes:
        print()
        print(
            "DRY RUN pabeigts. Lai veiktu izmaiņas, "
            "palaid skriptu ar parametru --apply."
        )


class SyncRunner:
    def __init__(
        self,
        config: SyncRunnerConfig,
        arguments: SyncArguments | None = None,
    ) -> None:
        self.config = config

        self.arguments = arguments or parse_sync_arguments(
            name=config.name,
            description=config.description,
            default_brand=config.default_brand,
        )

        self.statistics = SyncStatistics()

        self.supplier_products: list[Product] = []
        self.filtered_supplier_products: list[Product] = []

        self.woocommerce_products: list[Product] = []
        self.filtered_woocommerce_products: list[Product] = []

        self.comparison_result: Any = None
        self.changes: list[Any] = []

    def load_supplier_products(self) -> None:
        print("Lejupielādē piegādātāja produktus...")

        loaded = self.config.supplier_loader()
        self.supplier_products = ensure_product_list(loaded)

        self.filtered_supplier_products = filter_supplier_products(
            products=self.supplier_products,
            brand=self.arguments.brand,
            sku=self.arguments.sku,
        )

        self.statistics.supplier_loaded = len(self.supplier_products)
        self.statistics.supplier_filtered = len(
            self.filtered_supplier_products
        )

        print(
            f"{SYMBOL_OK} Piegādātāja produkti ielādēti: "
            f"{self.statistics.supplier_loaded}"
        )
        print(
            f"{SYMBOL_OK} Pēc piegādātāja filtra: "
            f"{self.statistics.supplier_filtered}"
        )

    def load_woocommerce_products(self) -> None:
        print()
        print("Ielādē WooCommerce produktus...")

        loaded = self.config.woocommerce_loader()
        self.woocommerce_products = ensure_product_list(loaded)

        self.filtered_woocommerce_products = filter_woocommerce_products(
            products=self.woocommerce_products,
            supplier_products=self.filtered_supplier_products,
            sku=self.arguments.sku,
        )

        self.statistics.woocommerce_loaded = len(
            self.woocommerce_products
        )
        self.statistics.woocommerce_filtered = len(
            self.filtered_woocommerce_products
        )

        print(
            f"{SYMBOL_OK} WooCommerce produkti ielādēti: "
            f"{self.statistics.woocommerce_loaded}"
        )
        print(
            f"{SYMBOL_OK} Pēc WooCommerce filtra: "
            f"{self.statistics.woocommerce_filtered}"
        )

    def compare(self) -> None:
        print()
        print("Salīdzina produktus...")

        self.comparison_result = self.config.comparator(
            self.filtered_supplier_products,
            self.filtered_woocommerce_products,
        )

        self.changes = list(
            self.config.change_selector(self.comparison_result)
        )

        comparison_statistics = build_statistics(
            supplier_loaded=self.supplier_products,
            supplier_filtered=self.filtered_supplier_products,
            woocommerce_loaded=self.woocommerce_products,
            woocommerce_filtered=self.filtered_woocommerce_products,
            result=self.comparison_result,
            changes=self.changes,
        )

        self.statistics.matching = comparison_statistics.matching
        self.statistics.changes = comparison_statistics.changes
        self.statistics.unchanged = comparison_statistics.unchanged
        self.statistics.supplier_only = (
            comparison_statistics.supplier_only
        )
        self.statistics.woocommerce_only = (
            comparison_statistics.woocommerce_only
        )
        self.statistics.duplicate_supplier = (
            comparison_statistics.duplicate_supplier
        )
        self.statistics.duplicate_woocommerce = (
            comparison_statistics.duplicate_woocommerce
        )

        print(f"{SYMBOL_OK} Sakrītošie SKU: {self.statistics.matching}")
        print(
            f"{SYMBOL_OK} {self.config.change_label}: "
            f"{self.statistics.changes}"
        )
        print(
            f"{SYMBOL_OK} Bez izmaiņām: "
            f"{self.statistics.unchanged}"
        )

    def print_changes(self) -> None:
        if not self.changes:
            print()
            print(f"{SYMBOL_OK} Izmaiņas nav nepieciešamas.")
            return

        print_section(self.config.change_label)

        total = len(self.changes)

        for index, change in enumerate(self.changes, start=1):
            self.config.change_printer(
                change,
                index,
                total,
                self.arguments.apply,
            )

    def apply_changes(self) -> None:
        if not self.changes:
            return

        if self.config.require_confirmation:
            confirmed = confirm_apply(
                item_count=len(self.changes),
                item_label=self.config.change_label.lower(),
                assume_yes=self.arguments.assume_yes,
            )

            if not confirmed:
                self.statistics.skipped += len(self.changes)

                print()
                print(
                    f"{SYMBOL_WARNING} Darbība atcelta. "
                    "WooCommerce izmaiņas nav veiktas."
                )
                return

        print_section("WooCommerce atjaunināšana")

        total = len(self.changes)

        for index, change in enumerate(self.changes, start=1):
            print(f"[{index}/{total}]", end=" ")

            try:
                result = self.config.updater(change)

                if result is False:
                    raise RuntimeError(
                        "Atjaunināšanas funkcija atgrieza False."
                    )

                self.statistics.updated += 1
                print(f"{SYMBOL_OK} Atjaunināts")

            except Exception as exc:
                self.statistics.failed += 1

                error_message = (
                    f"Izmaiņa {index}/{total}: {type(exc).__name__}: {exc}"
                )

                self.statistics.errors.append(error_message)

                print(f"{SYMBOL_ERROR} Kļūda: {exc}")

    def validate_loaded_products(self) -> bool:
        if not self.supplier_products:
            print()
            print(
                f"{SYMBOL_ERROR} Piegādātāja produktu saraksts ir tukšs."
            )
            return False

        if not self.filtered_supplier_products:
            print()
            print(
                f"{SYMBOL_WARNING} Nav atrasts neviens filtram "
                "atbilstošs piegādātāja produkts."
            )
            return False

        if not self.woocommerce_products:
            print()
            print(
                f"{SYMBOL_ERROR} WooCommerce produktu saraksts ir tukšs."
            )
            return False

        return True

    def run(self) -> int:
        started_at = time.monotonic()

        print_header(
            name=self.config.name,
            arguments=self.arguments,
        )

        try:
            self.load_supplier_products()

            if not self.filtered_supplier_products:
                self.statistics.elapsed_seconds = (
                    time.monotonic() - started_at
                )

                print_summary(
                    statistics=self.statistics,
                    arguments=self.arguments,
                    change_label=self.config.change_label,
                )

                return 1

            self.load_woocommerce_products()

            if not self.validate_loaded_products():
                self.statistics.elapsed_seconds = (
                    time.monotonic() - started_at
                )

                print_summary(
                    statistics=self.statistics,
                    arguments=self.arguments,
                    change_label=self.config.change_label,
                )

                return 1

            self.compare()

            print_result_details(
                result=self.comparison_result,
                show_missing_skus=self.config.show_missing_skus,
                show_duplicates=self.config.show_duplicates,
            )

            self.print_changes()

            if self.arguments.apply:
                self.apply_changes()

            self.statistics.elapsed_seconds = (
                time.monotonic() - started_at
            )

            print_summary(
                statistics=self.statistics,
                arguments=self.arguments,
                change_label=self.config.change_label,
            )

            return 1 if self.statistics.failed else 0

        except KeyboardInterrupt:
            self.statistics.elapsed_seconds = (
                time.monotonic() - started_at
            )

            print()
            print(f"{SYMBOL_WARNING} Darbību pārtrauca lietotājs.")

            return 130

        except Exception as exc:
            self.statistics.failed += 1
            self.statistics.elapsed_seconds = (
                time.monotonic() - started_at
            )

            error_message = f"{type(exc).__name__}: {exc}"
            self.statistics.errors.append(error_message)

            print()
            print(SEPARATOR)
            print(f"{SYMBOL_ERROR} KRITISKA KĻŪDA")
            print(SEPARATOR)
            print(error_message)
            print(
                f"Izpildes laiks: "
                f"{format_duration(self.statistics.elapsed_seconds)}"
            )
            print(SEPARATOR)

            return 1


def run_sync(
    config: SyncRunnerConfig,
    arguments: SyncArguments | None = None,
) -> int:
    runner = SyncRunner(
        config=config,
        arguments=arguments,
    )

    return runner.run()


def exit_with_sync_result(
    config: SyncRunnerConfig,
    arguments: SyncArguments | None = None,
) -> None:
    sys.exit(
        run_sync(
            config=config,
            arguments=arguments,
        )
    )