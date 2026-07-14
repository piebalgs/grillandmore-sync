import os
from dotenv import load_dotenv
import requests

load_dotenv()

BASE_URL = os.getenv("WC_URL")
KEY = os.getenv("WC_CONSUMER_KEY")
SECRET = os.getenv("WC_CONSUMER_SECRET")


def test_connection():
    url = f"{BASE_URL}/wp-json/wc/v3/products"

    response = requests.get(
        url,
        auth=(KEY, SECRET),
        params={"per_page": 5},
        timeout=30,
    )

    print(f"HTTP Status: {response.status_code}")

    if response.status_code == 200:
        products = response.json()
        print(f"✅ Atrasti {len(products)} produkti")

        for product in products:
            print(f"{product['sku']}  |  {product['name']}")
    else:
        print(response.text)


if __name__ == "__main__":
    test_connection()