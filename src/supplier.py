import os

import requests
from dotenv import load_dotenv
from lxml import etree

load_dotenv()

SUPPLIER_XML_URL = os.getenv("SUPPLIER_XML_URL")
SUPPLIER_USERNAME = os.getenv("SUPPLIER_USERNAME")
SUPPLIER_PASSWORD = os.getenv("SUPPLIER_PASSWORD")


def load_products():
    print("Lejupielādē XML...")

    response = requests.get(
        SUPPLIER_XML_URL,
        auth=(SUPPLIER_USERNAME, SUPPLIER_PASSWORD),
        timeout=60,
        headers={
            "User-Agent": "GrillAndMore Sync/1.0"
        },
    )

    response.raise_for_status()

    root = etree.fromstring(response.content)

    products = []

    for product in root.findall(".//product"):
        products.append({
            "sku": product.findtext("catalogue_number", "").strip(),
            "name": product.findtext("name", "").strip(),
            "price": float(product.findtext("price", "0")),
            "stock": int(product.findtext("instock", "0")),
            "barcode": product.findtext("barcode", "").strip(),
            "producer": product.findtext("producer", "").strip(),
        })

    print(f"Atrasti {len(products)} produkti.")

    return products


if __name__ == "__main__":
    products = load_products()

    print("\nPirmie 5 produkti:\n")

    for product in products[:5]:
        print(product)