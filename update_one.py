#!/usr/bin/env python3

import argparse

from src.supplier import load_products as load_supplier_products
from src.sync_engine import compare_products
from src.updater import update_product
from src.woocommerce import load_products as load_woocommerce_products


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Droši pārbauda vai atjaunina vienu WooCommerce produktu."
    )

    parser.add_argument(
        "sku",
        help="Produkta SKU, piemēram, 7032",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli veikt izmaiņas WooCommerce.",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()
    requested_sku = args.sku.strip().upper()

    supplier_products = load_supplier_products()
    woo_products = load_woocommerce_products()

    result = compare_products(
        supplier_products=supplier_products,
        woocommerce_products=woo_products,
    )

    matching_change = next(
        (
            change
            for change in result.changes
            if change.sku == requested_sku
        ),
        None,
    )

    if matching_change is None:
        if requested_sku in result.matching_skus:
            print(f"SKU {requested_sku}: izmaiņu nav.")
        else:
            print(
                f"SKU {requested_sku} nav atrasts abos datu avotos "
                "vai nav salīdzināms."
            )
        return

    print("\nPlānotās izmaiņas")
    print("=" * 60)
    print(f"SKU:          {matching_change.sku}")
    print(f"Nosaukums:    {matching_change.name}")
    print(f"WooCommerce ID: {matching_change.woo_id}")

    if matching_change.price_changed:
        print(
            f"Cena:         {matching_change.price_old} "
            f"→ {matching_change.price_new}"
        )

    if matching_change.stock_changed:
        print(
            f"Atlikums:     {matching_change.stock_old} "
            f"→ {matching_change.stock_new}"
        )

    if not args.apply:
        print("\nDRY RUN — veikalā nekas netika mainīts.")
        print(
            f"Lai veiktu izmaiņas, palaid: "
            f"python3 update_one.py {requested_sku} --apply"
        )
        return

    print("\nVeic atjaunināšanu...")

    updated_product = update_product(
        matching_change.woo_id,
        regular_price=(
            matching_change.price_new
            if matching_change.price_changed
            else None
        ),
        stock_quantity=(
            matching_change.stock_new
            if matching_change.stock_changed
            else None
        ),
    )

    print("✅ Produkts veiksmīgi atjaunināts.")
    print(f"SKU:      {updated_product.get('sku', '')}")
    print(f"Cena:     {updated_product.get('regular_price', '')}")
    print(f"Atlikums: {updated_product.get('stock_quantity', '')}")
    print(f"Statuss:  {updated_product.get('stock_status', '')}")


if __name__ == "__main__":
    main()