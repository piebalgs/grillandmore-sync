import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("WC_URL", "").rstrip("/")
KEY = os.getenv("WC_CONSUMER_KEY")
SECRET = os.getenv("WC_CONSUMER_SECRET")


def load_products():
    if not BASE_URL or not KEY or not SECRET:
        raise RuntimeError("WooCommerce piekļuves dati nav norādīti .env failā.")

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
        print(f"  Nolasīta {page}. lapa — kopā {len(products)} produkti.")

        if len(page_products) < 100:
            break

        page += 1

    print(f"WooCommerce atrasti {len(products)} produkti.")
    return products


if __name__ == "__main__":
    products = load_products()

    print("\nPirmie 5 produkti:\n")

    for product in products[:5]:
        print(f"{product.get('sku', '')} | {product.get('name', '')}")