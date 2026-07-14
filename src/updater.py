from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")


def update_product(
    product_id: int,
    *,
    regular_price: Decimal | None = None,
    stock_quantity: int | None = None,
) -> dict[str, Any]:
    if not WC_URL or not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        raise RuntimeError(
            "WooCommerce piekļuves dati nav norādīti .env failā."
        )

    payload: dict[str, Any] = {}

    if regular_price is not None:
        payload["regular_price"] = format(regular_price, "f")

    if stock_quantity is not None:
        payload["manage_stock"] = True
        payload["stock_quantity"] = stock_quantity
        payload["stock_status"] = (
            "instock" if stock_quantity > 0 else "outofstock"
        )

    if not payload:
        raise ValueError("Nav norādīts neviens atjaunināmais lauks.")

    response = requests.put(
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
        auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
        json=payload,
        timeout=60,
    )

    response.raise_for_status()
    return response.json()