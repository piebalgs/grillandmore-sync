from __future__ import annotations

import sys
import time
from typing import Any, Callable, Iterable

import sync_prices
import sync_stock
from src import supplier, woocommerce
from src.sync_common import SyncContext, ensure_product_list, run_sync


SEPARATOR = "=" * 72


Product = dict[str, Any]


def format_duration(elapsed_seconds: float) -> str:
    """
    Pārveido izpildes laiku formātā HH:MM:SS.
    """
    total_seconds = max(0, int(round(elapsed_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def print_section(title: str) -> None:
    """
    Parāda skaidri atdalītu sinhronizācijas posma virsrakstu.
    """
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def print_total_duration(elapsed_seconds: float) -> None:
    """
    Parāda visas produktu sinhronizācijas kopējo izpildes laiku.
    """
    print()
    print(SEPARATOR)
    print("KOPĒJAIS IZPILDES LAIKS")
    print(SEPARATOR)
    print(
        "Kopējais izpildes laiks:     "
        f"{format_duration(elapsed_seconds)}"
    )
    print(SEPARATOR)


def load_product_list(
    loader: Callable[[], Iterable[Product] | None],
    source_name: str,
) -> list[Product]:
    """
    Izsauc produktu ielādes funkciju un garantē saraksta rezultātu.
    """
    products: Iterable[Product] | None = loader()
    product_list = ensure_product_list(products)

    if not product_list:
        raise RuntimeError(
            f"{source_name} produktu saraksts ir tukšs."
        )

    return product_list


def build_context() -> SyncContext:
    """
    Vienu reizi ielādē piegādātāja un WooCommerce produktus.

    Izveidotais konteksts pēc tam tiek nodots visiem sinhronizācijas
    posmiem, lai tie izmantotu vienas un tās pašas produktu kolekcijas.
    """
    print_section("KOPĪGO DATU IELĀDE")

    print("Lejupielādē piegādātāja produktu kolekciju...")
    supplier_products = load_product_list(
        loader=supplier.load_products,
        source_name="Piegādātāja",
    )
    print(
        "Piegādātāja produkti kopīgajā kontekstā: "
        f"{len(supplier_products)}"
    )

    print()
    print("Ielādē WooCommerce produktu kolekciju...")
    woocommerce_products = load_product_list(
        loader=woocommerce.load_products,
        source_name="WooCommerce",
    )
    print(
        "WooCommerce produkti kopīgajā kontekstā: "
        f"{len(woocommerce_products)}"
    )

    return SyncContext(
        supplier_products=supplier_products,
        woocommerce_products=woocommerce_products,
    )


def run_price_sync(context: SyncContext) -> int:
    """
    Palaiž cenu sinhronizāciju ar kopīgo produktu kontekstu.
    """
    return run_sync(
        config=sync_prices.build_config(),
        context=context,
    )


def run_stock_sync(context: SyncContext) -> int:
    """
    Palaiž atlikumu sinhronizāciju ar to pašu produktu kontekstu.
    """
    return run_sync(
        config=sync_stock.build_config(),
        context=context,
    )


def run() -> int:
    """
    Secīgi palaiž cenu un noliktavas atlikumu sinhronizāciju.

    Piegādātāja un WooCommerce produkti tiek ielādēti tikai vienu reizi
    un saglabāti kopīgā SyncContext objektā. Abi sinhronizācijas posmi
    izmanto šīs pašas produktu kolekcijas.

    Cenu sinhronizācija tiek izpildīta pirmā. Ja tā beidzas ar kļūdu
    vai lietotājs to pārtrauc, atlikumu sinhronizācija netiek palaista.

    Rezultāta kodi:
    0 — abi sinhronizācijas posmi pabeigti veiksmīgi;
    1 — datu ielāde vai vismaz viens posms beidzās ar kļūdu;
    130 — darbību pārtrauca lietotājs.
    """
    started_at = time.monotonic()

    try:
        context = build_context()

        print_section("1. POSMS — CENU SINHRONIZĀCIJA")

        price_result = run_price_sync(context)

        if price_result != 0:
            print()
            print(
                "Cenu sinhronizācija netika pabeigta veiksmīgi. "
                "Atlikumu sinhronizācija netiks palaista."
            )
            return price_result

        print_section("2. POSMS — ATLIKUMU SINHRONIZĀCIJA")

        stock_result = run_stock_sync(context)

        if stock_result != 0:
            print()
            print(
                "Atlikumu sinhronizācija netika pabeigta veiksmīgi."
            )
            return stock_result

        print()
        print(SEPARATOR)
        print("PRODUKTU SINHRONIZĀCIJA PABEIGTA VEIKSMĪGI")
        print(SEPARATOR)

        return 0

    except KeyboardInterrupt:
        print()
        print("Sinhronizāciju pārtrauca lietotājs.")
        return 130

    except Exception as exc:
        print()
        print(SEPARATOR)
        print("PRODUKTU SINHRONIZĀCIJA BEIDZĀS AR KĻŪDU")
        print(SEPARATOR)
        print(f"{type(exc).__name__}: {exc}")
        print(SEPARATOR)
        return 1

    finally:
        elapsed_seconds = time.monotonic() - started_at
        print_total_duration(elapsed_seconds)


def main() -> None:
    """
    Palaiž kopējo produktu sinhronizāciju kā termināļa komandu.
    """
    sys.exit(run())


if __name__ == "__main__":
    main()
