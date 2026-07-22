from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from config import (
    DEFAULT_BRAND,
    PROJECT_NAME,
    PROJECT_VERSION,
    SEPARATOR,
    SUBSEPARATOR,
    SYMBOL_ERROR,
    SYMBOL_OK,
    SYMBOL_WARNING,
)


Product = dict[str, Any]
Change = Any
Comparison = Any

ProductLoader = Callable[[], Iterable[Product]]
Comparator = Callable[[list[Product], list[Product]], Comparison]
ChangeSelector = Callable[[Comparison], Sequence[Change]]
ChangeUpdater = Callable[[Change], Any]
ChangePrinter = Callable[[Change, int, int, bool], None]
UnchangedPrinter = Callable[
    [Comparison, list[Product], list[Product]],
    None,
]


@dataclass
class SyncContext:
    supplier_products: list[Product] = field(default_factory=list)
    woocommerce_products: list[Product] = field(default_factory=list)


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
    unchanged: int = 0
    changes: int = 0

    updated: int = 0
    skipped: int = 0
    failed: int = 0

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

    change_printer: ChangePrinter
    updater: ChangeUpdater

    description: str | None = None
    default_brand: str = DEFAULT_BRAND

    unchanged_printer: UnchangedPrinter | None = None

    require_confirmation: bool = True
    show_missing_skus: bool = True
    show_duplicates: bool = True


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_sku(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_brand(value: Any) -> str:
    return normalize_text(value).upper()


def product_sku(product: Product) -> str:
    return normalize_sku(
        product.get("sku")
        or product.get("catalogue_number")
        or product.get("catalog_number")
    )


def product_brand(product: Product) -> str:
    return normalize_brand(
        product.get("producer")
        or product.get("brand")
        or product.get("manufacturer")
    )


def ensure_product_list(
    products: Iterable[Product] | None,
) -> list[Product]:
    if products is None:
        return []

    if isinstance(products, list):
        return products

    return list(products)


def use_brand_filter(brand: str | None) -> bool:
    normalized = normalize_brand(brand)

    return bool(
        normalized
        and normalized not in {
            "ALL",
            "*",
            "VISI",
            "VISI ZĪMOLI",
        }
    )


def filter_supplier_products(
    products: Iterable[Product],
    brand: str | None,
    sku: str | None,
) -> list[Product]:
    normalized_brand = normalize_brand(brand)
    normalized_sku = normalize_sku(sku)

    filtered: list[Product] = []

    for product in products:
        current_sku = product_sku(product)

        if normalized_sku and current_sku != normalized_sku:
            continue

        if use_brand_filter(normalized_brand):
            if normalized_brand not in product_brand(product):
                continue

        filtered.append(product)

    return filtered


def filter_woocommerce_products(
    products: Iterable[Product],
    supplier_products: Iterable[Product],
    sku: str | None,
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
    description: str | None,
    default_brand: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=name,
        description=description,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Veikt reālas izmaiņas WooCommerce.",
    )

    parser.add_argument(
        "--brand",
        default=default_brand,
        help=(
            "Piegādātāja zīmola filtrs. "
            f"Noklusējums: {default_brand}. "
            "Lai apstrādātu visus zīmolus, norādi --brand ALL."
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
    description: str | None,
    default_brand: str,
) -> SyncArguments:
    parser = build_argument_parser(
        name=name,
        description=description,
        default_brand=default_brand,
    )

    arguments = parser.parse_args()

    return SyncArguments(
        apply=bool(arguments.apply),
        brand=normalize_text(arguments.brand),
        sku=normalize_text(arguments.sku) or None,
        show_unchanged=bool(arguments.show_unchanged),
        assume_yes=bool(arguments.yes),
    )


def format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))

    minutes, seconds_left = divmod(rounded, 60)
    hours, minutes_left = divmod(minutes, 60)

    if hours:
        return (
            f"{hours:02d}:"
            f"{minutes_left:02d}:"
            f"{seconds_left:02d}"
        )

    return f"{minutes_left:02d}:{seconds_left:02d}"


def print_header(
    config: SyncRunnerConfig,
    arguments: SyncArguments,
) -> None:
    mode = "APPLY" if arguments.apply else "DRY RUN"

    brand = arguments.brand or "nav"

    if not use_brand_filter(brand):
        brand = "visi zīmoli"

    print(SEPARATOR)
    print(config.name)
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


def result_list(
    result: Comparison,
    attribute_name: str,
) -> list[Any]:
    value = getattr(result, attribute_name, None)

    if value is None:
        return []

    return list(value)


def matching_skus(result: Comparison) -> list[str]:
    return [
        normalize_sku(sku)
        for sku in result_list(result, "matching_skus")
        if normalize_sku(sku)
    ]


def supplier_only_skus(result: Comparison) -> list[str]:
    return [
        normalize_sku(sku)
        for sku in result_list(result, "supplier_only_skus")
        if normalize_sku(sku)
    ]


def woocommerce_only_skus(result: Comparison) -> list[str]:
    return [
        normalize_sku(sku)
        for sku in result_list(result, "woocommerce_only_skus")
        if normalize_sku(sku)
    ]


def duplicate_supplier_skus(result: Comparison) -> list[str]:
    return [
        normalize_sku(sku)
        for sku in result_list(
            result,
            "duplicate_supplier_skus",
        )
        if normalize_sku(sku)
    ]


def duplicate_woocommerce_skus(
    result: Comparison,
) -> list[str]:
    return [
        normalize_sku(sku)
        for sku in result_list(
            result,
            "duplicate_woocommerce_skus",
        )
        if normalize_sku(sku)
    ]


def print_sku_list(
    title: str,
    skus: Sequence[str],
) -> None:
    if not skus:
        return

    print_section(title)

    for sku in skus:
        print(f"- {sku}")


def confirm_apply(
    item_count: int,
    change_label: str,
    assume_yes: bool,
) -> bool:
    if assume_yes:
        return True

    print()
    print(SEPARATOR)
    print(
        f"{SYMBOL_WARNING} UZMANĪBU: WooCommerce tiks veiktas "
        f"{item_count} izmaiņas: {change_label.lower()}."
    )
    print("Lai turpinātu, ieraksti: APPLY")
    print(SEPARATOR)

    try:
        answer = input("> ").strip()
    except EOFError:
        return False

    return answer == "APPLY"


class SyncRunner:
    def __init__(
        self,
        config: SyncRunnerConfig,
        arguments: SyncArguments | None = None,
        context: SyncContext | None = None,
        supplier_products: Iterable[Product] | None = None,
        woocommerce_products: Iterable[Product] | None = None,
    ) -> None:
        self.config = config

        if context is not None and (
            supplier_products is not None
            or woocommerce_products is not None
        ):
            raise ValueError(
                "Norādi vai nu context, vai atsevišķus produktu "
                "sarakstus, nevis abus vienlaikus."
            )

        self.arguments = arguments or parse_sync_arguments(
            name=config.name,
            description=config.description,
            default_brand=config.default_brand,
        )

        self.statistics = SyncStatistics()

        if context is None:
            context = SyncContext(
                supplier_products=ensure_product_list(
                    supplier_products
                ),
                woocommerce_products=ensure_product_list(
                    woocommerce_products
                ),
            )

        self.context = context

        self._supplier_products_provided = bool(
            self.context.supplier_products
        )
        self._woocommerce_products_provided = bool(
            self.context.woocommerce_products
        )

        self.supplier_products = self.context.supplier_products
        self.filtered_supplier_products: list[Product] = []

        self.woocommerce_products = self.context.woocommerce_products
        self.filtered_woocommerce_products: list[Product] = []

        self.comparison_result: Comparison | None = None
        self.changes: list[Change] = []

    def load_supplier(self) -> None:
        if self._supplier_products_provided:
            print("Izmanto jau ielādētus piegādātāja produktus...")
        else:
            print("Lejupielādē piegādātāja produktus...")

            self.supplier_products = ensure_product_list(
                self.config.supplier_loader()
            )
            self.context.supplier_products = self.supplier_products

        self.filtered_supplier_products = filter_supplier_products(
            products=self.supplier_products,
            brand=self.arguments.brand,
            sku=self.arguments.sku,
        )

        self.statistics.supplier_loaded = len(
            self.supplier_products
        )
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

    def load_woocommerce(self) -> None:
        print()

        if self._woocommerce_products_provided:
            print("Izmanto jau ielādētus WooCommerce produktus...")
        else:
            print("Ielādē WooCommerce produktus...")

            self.woocommerce_products = ensure_product_list(
                self.config.woocommerce_loader()
            )
            self.context.woocommerce_products = (
                self.woocommerce_products
            )

        self.filtered_woocommerce_products = (
            filter_woocommerce_products(
                products=self.woocommerce_products,
                supplier_products=self.filtered_supplier_products,
                sku=self.arguments.sku,
            )
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

    def validate_products(self) -> bool:
        if not self.supplier_products:
            print()
            print(
                f"{SYMBOL_ERROR} Piegādātāja produktu "
                "saraksts ir tukšs."
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
                f"{SYMBOL_ERROR} WooCommerce produktu "
                "saraksts ir tukšs."
            )
            return False

        return True

    def compare(self) -> None:
        print()
        print("Salīdzina produktus...")

        self.comparison_result = self.config.comparator(
            self.filtered_supplier_products,
            self.filtered_woocommerce_products,
        )

        self.changes = list(
            self.config.change_selector(
                self.comparison_result
            )
        )

        matching = matching_skus(self.comparison_result)

        self.statistics.matching = len(matching)
        self.statistics.changes = len(self.changes)
        self.statistics.unchanged = max(
            0,
            self.statistics.matching - self.statistics.changes,
        )

        self.statistics.supplier_only = len(
            supplier_only_skus(self.comparison_result)
        )
        self.statistics.woocommerce_only = len(
            woocommerce_only_skus(self.comparison_result)
        )
        self.statistics.duplicate_supplier = len(
            duplicate_supplier_skus(self.comparison_result)
        )
        self.statistics.duplicate_woocommerce = len(
            duplicate_woocommerce_skus(self.comparison_result)
        )

        print(
            f"{SYMBOL_OK} Sakrītošie SKU: "
            f"{self.statistics.matching}"
        )
        print(
            f"{SYMBOL_OK} {self.config.change_label}: "
            f"{self.statistics.changes}"
        )
        print(
            f"{SYMBOL_OK} Bez izmaiņām: "
            f"{self.statistics.unchanged}"
        )

    def print_comparison_details(self) -> None:
        if self.comparison_result is None:
            return

        if self.config.show_duplicates:
            print_sku_list(
                "Dublikāti piegādātāja datos",
                duplicate_supplier_skus(
                    self.comparison_result
                ),
            )

            print_sku_list(
                "Dublikāti WooCommerce",
                duplicate_woocommerce_skus(
                    self.comparison_result
                ),
            )

        if self.config.show_missing_skus:
            print_sku_list(
                "Piegādātāja SKU, kas nav atrasti WooCommerce",
                supplier_only_skus(
                    self.comparison_result
                ),
            )

            print_sku_list(
                "WooCommerce SKU, kas nav atrasti piegādātāja datos",
                woocommerce_only_skus(
                    self.comparison_result
                ),
            )

        if (
            self.arguments.show_unchanged
            and self.config.unchanged_printer is not None
        ):
            self.config.unchanged_printer(
                self.comparison_result,
                self.filtered_supplier_products,
                self.filtered_woocommerce_products,
            )

    def print_changes(self) -> None:
        if not self.changes:
            print()
            print(
                f"{SYMBOL_OK} Izmaiņas nav nepieciešamas."
            )
            return

        print_section(self.config.change_label)

        total = len(self.changes)

        for index, change in enumerate(
            self.changes,
            start=1,
        ):
            self.config.change_printer(
                change,
                index,
                total,
                self.arguments.apply,
            )

            if self.arguments.dry_run:
                print(
                    "  Rezultāts:        "
                    "DRY RUN — izmaiņas nav veiktas"
                )

    def apply_changes(self) -> None:
        if not self.changes:
            return

        if self.config.require_confirmation:
            confirmed = confirm_apply(
                item_count=len(self.changes),
                change_label=self.config.change_label,
                assume_yes=self.arguments.assume_yes,
            )

            if not confirmed:
                self.statistics.skipped = len(self.changes)

                print()
                print(
                    f"{SYMBOL_WARNING} Darbība atcelta. "
                    "WooCommerce izmaiņas nav veiktas."
                )
                return

        print_section("WooCommerce atjaunināšana")

        total = len(self.changes)

        for index, change in enumerate(
            self.changes,
            start=1,
        ):
            print(f"[{index}/{total}]", end=" ")

            try:
                response = self.config.updater(change)

                if response is False:
                    raise RuntimeError(
                        "Atjaunināšanas funkcija atgrieza False."
                    )

                self.statistics.updated += 1
                print(f"{SYMBOL_OK} ATJAUNINĀTS")

            except Exception as exc:
                self.statistics.failed += 1

                message = (
                    f"Izmaiņa {index}/{total}: "
                    f"{type(exc).__name__}: {exc}"
                )

                self.statistics.errors.append(message)

                print(
                    f"{SYMBOL_ERROR} KĻŪDA — {exc}"
                )

    def print_summary(self) -> None:
        mode = (
            "APPLY"
            if self.arguments.apply
            else "DRY RUN"
        )

        print()
        print(SEPARATOR)
        print("Kopsavilkums")
        print(SEPARATOR)
        print(f"Režīms:                     {mode}")
        print(
            f"Piegādātāja produkti:       "
            f"{self.statistics.supplier_loaded}"
        )
        print(
            f"Pēc piegādātāja filtra:     "
            f"{self.statistics.supplier_filtered}"
        )
        print(
            f"WooCommerce produkti:       "
            f"{self.statistics.woocommerce_loaded}"
        )
        print(
            f"Pēc WooCommerce filtra:     "
            f"{self.statistics.woocommerce_filtered}"
        )
        print(
            f"Sakrītošie SKU:             "
            f"{self.statistics.matching}"
        )
        print(
            f"{self.config.change_label}:"
            f"{' ' * max(1, 28 - len(self.config.change_label))}"
            f"{self.statistics.changes}"
        )
        print(
            f"Bez izmaiņām:               "
            f"{self.statistics.unchanged}"
        )
        print(
            f"Atjaunināti:                "
            f"{self.statistics.updated}"
        )
        print(
            f"Izlaisti:                   "
            f"{self.statistics.skipped}"
        )
        print(
            f"Kļūdas:                     "
            f"{self.statistics.failed}"
        )
        print(
            f"Tikai piegādātāja datos:    "
            f"{self.statistics.supplier_only}"
        )
        print(
            f"Tikai WooCommerce datos:    "
            f"{self.statistics.woocommerce_only}"
        )
        print(
            f"Piegādātāja dublikāti:      "
            f"{self.statistics.duplicate_supplier}"
        )
        print(
            f"WooCommerce dublikāti:      "
            f"{self.statistics.duplicate_woocommerce}"
        )
        print(
            f"Posma izpildes laiks:       "
            f"{format_duration(self.statistics.elapsed_seconds)}"
        )
        print(SEPARATOR)

        if self.statistics.errors:
            print_section("Kļūdu apraksti")

            for error in self.statistics.errors:
                print(f"- {error}")

        if (
            self.arguments.dry_run
            and self.statistics.changes
        ):
            print()
            print(
                "DRY RUN pabeigts. Lai veiktu izmaiņas, "
                "palaid skriptu ar parametru --apply."
            )

    def run(self) -> int:
        started_at = time.monotonic()

        print_header(
            config=self.config,
            arguments=self.arguments,
        )

        try:
            self.load_supplier()

            if not self.filtered_supplier_products:
                return 1

            self.load_woocommerce()

            if not self.validate_products():
                return 1

            self.compare()
            self.print_comparison_details()
            self.print_changes()

            if self.arguments.apply:
                self.apply_changes()

            return 1 if self.statistics.failed else 0

        except KeyboardInterrupt:
            print()
            print(
                f"{SYMBOL_WARNING} Darbību pārtrauca lietotājs."
            )
            return 130

        except Exception as exc:
            self.statistics.failed += 1

            message = f"{type(exc).__name__}: {exc}"
            self.statistics.errors.append(message)

            print()
            print(SEPARATOR)
            print(f"{SYMBOL_ERROR} KRITISKA KĻŪDA")
            print(SEPARATOR)
            print(message)
            print(SEPARATOR)

            return 1

        finally:
            self.statistics.elapsed_seconds = (
                time.monotonic() - started_at
            )

            self.print_summary()


def run_sync(
    config: SyncRunnerConfig,
    arguments: SyncArguments | None = None,
    context: SyncContext | None = None,
    supplier_products: Iterable[Product] | None = None,
    woocommerce_products: Iterable[Product] | None = None,
) -> int:
    return SyncRunner(
        config=config,
        arguments=arguments,
        context=context,
        supplier_products=supplier_products,
        woocommerce_products=woocommerce_products,
    ).run()


def exit_with_sync_result(
    config: SyncRunnerConfig,
    arguments: SyncArguments | None = None,
    context: SyncContext | None = None,
    supplier_products: Iterable[Product] | None = None,
    woocommerce_products: Iterable[Product] | None = None,
) -> None:
    sys.exit(
        run_sync(
            config=config,
            arguments=arguments,
            context=context,
            supplier_products=supplier_products,
            woocommerce_products=woocommerce_products,
        )
    )
