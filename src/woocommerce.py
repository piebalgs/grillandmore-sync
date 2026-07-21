import os

import requests
from dotenv import load_dotenv

from src.pricing import prepare_price_update

load_dotenv()

BASE_URL = os.getenv("WC_URL", "").rstrip("/")
KEY = os.getenv("WC_CONSUMER_KEY")
SECRET = os.getenv("WC_CONSUMER_SECRET")


def _check_configuration():
    if not BASE_URL or not KEY or not SECRET:
        raise RuntimeError(
            "WooCommerce piekļuves dati nav norādīti .env failā."
        )


def load_products():
    _check_configuration()

    products = []
    page = 1

    print("Nolasa WooCommerce produktus...")

    while True:
        response = requests.get(
            f"{BASE_URL}/wp-json/wc/v3/products",
            auth=(KEY, SECRET),
            params={
                "per_page": 100,
                "page": page,
                "status": "any",
            },
            timeout=60,
        )

        response.raise_for_status()

        page_products = response.json()

        if not page_products:
            break

        products.extend(page_products)

        print(
            f"  Nolasīta {page}. lapa — kopā {len(products)} produkti."
        )

        if len(page_products) < 100:
            break

        page += 1

    print(f"WooCommerce atrasti {len(products)} produkti.")

    return products


def get_product_by_sku(sku):
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

    response = requests.get(
        f"{BASE_URL}/wp-json/wc/v3/products",
        auth=(KEY, SECRET),
        params={
            "sku": normalized_sku,
            "status": "any",
            "per_page": 100,
        },
        timeout=60,
    )

    response.raise_for_status()

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


def update_product(product_id: int, payload: dict) -> dict:
    """
    Universāla WooCommerce produkta atjaunināšana.
    """

    _check_configuration()

    response = requests.put(
        f"{BASE_URL}/wp-json/wc/v3/products/{product_id}",
        auth=(KEY, SECRET),
        json=payload,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def update_product_price(product_id: int, gross_price) -> dict:
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
) -> dict:
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