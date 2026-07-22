from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from src.pricing import prepare_price_update


load_dotenv()

BASE_URL = os.getenv("WC_URL", "").rstrip("/")
KEY = os.getenv("WC_CONSUMER_KEY")
SECRET = os.getenv("WC_CONSUMER_SECRET")

REQUEST_TIMEOUT = 120
MAX_REQUEST_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3

_PRODUCTS_CACHE: list[dict[str, Any]] | None = None


def _check_configuration() -> None:
    """
    Pārbauda, vai .env failā ir norādīti WooCommerce piekļuves dati.
    """
    if not BASE_URL or not KEY or not SECRET:
        raise RuntimeError(
            "WooCommerce piekļuves dati nav norādīti .env failā."
        )


def _request(
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    """
    Izpilda WooCommerce HTTP pieprasījumu ar automātiskiem atkārtojumiem.

    ReadTimeout un savienojuma kļūdas gadījumā pieprasījums tiek
    atkārtots līdz MAX_REQUEST_ATTEMPTS reizēm. HTTP kļūdas, piemēram,
    401, 403 vai 500, netiek klusējot ignorētas.
    """
    kwargs.setdefault("auth", (KEY, SECRET))
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)

    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                **kwargs,
            )
            response.raise_for_status()
            return response

        except (
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectionError,
        ) as error:
            if attempt >= MAX_REQUEST_ATTEMPTS:
                raise

            wait_seconds = RETRY_DELAY_SECONDS * attempt

            print(
                "  ⚠ WooCommerce API savienojuma kļūda: "
                f"{error.__class__.__name__}."
            )
            print(
                f"  Atkārtots mēģinājums pēc {wait_seconds} sekundēm "
                f"({attempt + 1}/{MAX_REQUEST_ATTEMPTS})..."
            )

            time.sleep(wait_seconds)

    raise RuntimeError("WooCommerce API pieprasījumu neizdevās izpildīt.")


def clear_products_cache() -> None:
    """
    Notīra šī Python procesa WooCommerce produktu kešatmiņu.
    """
    global _PRODUCTS_CACHE
    _PRODUCTS_CACHE = None


def set_products_cache(products: list[dict[str, Any]]) -> None:
    """
    Saglabā jau ielādētu WooCommerce produktu sarakstu kešatmiņā.
    """
    global _PRODUCTS_CACHE
    _PRODUCTS_CACHE = list(products)


def load_products(
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """
    Nolasa visus WooCommerce produktus.

    Viena Python procesa laikā produktu katalogs tiek ielādēts tikai
    vienreiz. Nākamie izsaukumi izmanto kešatmiņu, tāpēc cenu un atlikumu
    sinhronizācijai nav atkārtoti jānoslogo WooCommerce REST API.

    force_refresh=True piespiedu kārtā nolasa katalogu no jauna.
    """
    global _PRODUCTS_CACHE

    _check_configuration()

    if _PRODUCTS_CACHE is not None and not force_refresh:
        print(
            "Izmanto WooCommerce produktu kešatmiņu "
            f"({len(_PRODUCTS_CACHE)} produkti)."
        )
        return list(_PRODUCTS_CACHE)

    products: list[dict[str, Any]] = []
    page = 1

    print("Nolasa WooCommerce produktus...")

    while True:
        response = _request(
            method="GET",
            url=f"{BASE_URL}/wp-json/wc/v3/products",
            params={
                "per_page": 100,
                "page": page,
                "status": "any",
            },
        )

        page_products = response.json()

        if not isinstance(page_products, list):
            raise RuntimeError(
                "WooCommerce API atgrieza neparedzētu produktu sarakstu."
            )

        if not page_products:
            break

        products.extend(page_products)

        print(
            f"  Nolasīta {page}. lapa — kopā {len(products)} produkti."
        )

        if len(page_products) < 100:
            break

        page += 1

    _PRODUCTS_CACHE = list(products)

    print(f"WooCommerce atrasti {len(products)} produkti.")

    return list(products)


def get_product_by_sku(sku: Any) -> dict[str, Any] | None:
    """
    Nolasa vienu WooCommerce produktu pēc precīza SKU.
    """
    _check_configuration()

    normalized_sku = str(sku or "").strip().upper()

    if not normalized_sku:
        raise ValueError("SKU nedrīkst būt tukšs.")

    print(
        f"Nolasa WooCommerce produktu ar SKU {normalized_sku}..."
    )

    response = _request(
        method="GET",
        url=f"{BASE_URL}/wp-json/wc/v3/products",
        params={
            "sku": normalized_sku,
            "status": "any",
            "per_page": 100,
        },
    )

    products = response.json()

    if not isinstance(products, list):
        raise RuntimeError(
            "WooCommerce API atgrieza neparedzētu atbildi."
        )

    for product in products:
        if not isinstance(product, dict):
            continue

        product_sku = str(
            product.get("sku") or ""
        ).strip().upper()

        if product_sku == normalized_sku:
            print(
                "WooCommerce produkts atrasts: "
                f"{product.get('name', '')}"
            )
            return product

    print(
        f"WooCommerce produkts ar SKU "
        f"{normalized_sku} netika atrasts."
    )

    return None


def update_product(
    product_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Universāli atjaunina vienu WooCommerce produktu.
    """
    _check_configuration()

    if product_id <= 0:
        raise ValueError("WooCommerce produkta ID jābūt pozitīvam.")

    response = _request(
        method="PUT",
        url=f"{BASE_URL}/wp-json/wc/v3/products/{product_id}",
        json=payload,
    )

    updated_product = response.json()

    if not isinstance(updated_product, dict):
        raise RuntimeError(
            "WooCommerce API pēc atjaunināšanas atgrieza "
            "neparedzētu atbildi."
        )

    return updated_product


def update_product_price(
    product_id: int,
    gross_price: Any,
) -> dict[str, Any]:
    """
    Atjaunina produkta regular_price.
    """
    payload = prepare_price_update(gross_price)

    return update_product(
        product_id=product_id,
        payload=payload,
    )


def update_product_stock(
    product_id: int,
    stock_quantity: int,
) -> dict[str, Any]:
    """
    Atjaunina produkta noliktavas atlikumu.
    """
    payload = {
        "manage_stock": True,
        "stock_quantity": int(stock_quantity),
    }

    return update_product(
        product_id=product_id,
        payload=payload,
    )


if __name__ == "__main__":
    products = load_products()

    print("\nPirmie 5 produkti:\n")

    for product in products[:5]:
        print(
            f"{product.get('sku', '')} | "
            f"{product.get('name', '')}"
        )
