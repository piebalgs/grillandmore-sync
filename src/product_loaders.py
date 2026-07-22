from __future__ import annotations

from types import ModuleType
from typing import Any, Callable, Iterable, Sequence

from src import supplier, woocommerce


Product = dict[str, Any]
ProductLoader = Callable[[], Iterable[Product] | None]


def ensure_product_list(
    products: Iterable[Product] | None,
) -> list[Product]:
    """
    Pārveido produktu kolekciju par sarakstu.

    Ja ielādes funkcija atgriež None, tiek atgriezts tukšs saraksts.
    Ja rezultāts jau ir saraksts, tas netiek kopēts.
    """
    if products is None:
        return []

    if isinstance(products, list):
        return products

    return list(products)


def resolve_callable(
    module: ModuleType,
    possible_names: Sequence[str],
    description: str,
) -> Callable[..., Any]:
    """
    Atrod modulī pirmo pieejamo izsaucamo funkciju.

    Tas saglabā savietojamību, ja vienas un tās pašas darbības
    funkcijas nosaukums dažādās projekta versijās atšķiras.
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


def load_products_from_module(
    module: ModuleType,
    possible_names: Sequence[str],
    description: str,
) -> list[Product]:
    """
    Atrod moduļa produktu ielādes funkciju, izsauc to un garantē
    saraksta rezultātu.
    """
    loader = resolve_callable(
        module=module,
        possible_names=possible_names,
        description=description,
    )

    return ensure_product_list(loader())


def load_supplier_products() -> list[Product]:
    """
    Ielādē visus piegādātāja produktus.
    """
    return load_products_from_module(
        module=supplier,
        possible_names=(
            "load_products",
            "load_supplier_products",
            "get_products",
        ),
        description="piegādātāja produktu ielādei",
    )


def load_woocommerce_products() -> list[Product]:
    """
    Ielādē visus WooCommerce produktus.
    """
    return load_products_from_module(
        module=woocommerce,
        possible_names=(
            "load_products",
            "load_woocommerce_products",
            "get_products",
        ),
        description="WooCommerce produktu ielādei",
    )