from src.woocommerce import load_products


TARGET_SKUS = {"AS18K", "AS22K"}


def main() -> None:
    products = load_products()

    found = 0

    for product in products:
        sku = str(product.get("sku") or "").strip()

        if sku not in TARGET_SKUS:
            continue

        found += 1

        print("=" * 100)
        print(f"SKU: {sku}")
        print(f"Nosaukums: {product.get('name')}")
        print(f"Produkta ID: {product.get('id')}")
        print(f"Attēlu skaits: {len(product.get('images') or [])}")
        print()

        for index, image in enumerate(product.get("images") or [], start=1):
            print(
                f"{index:2d}. "
                f"id={image.get('id')} | "
                f"name={image.get('name')} | "
                f"alt={image.get('alt')} | "
                f"src={image.get('src')}"
            )

    if found == 0:
        print("Produkti AS18K un AS22K netika atrasti.")


if __name__ == "__main__":
    main()


