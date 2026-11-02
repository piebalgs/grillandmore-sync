
"""Preview manual grill descriptions without WooCommerce writes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
    GrillDescriptionResult,
)
from src.descriptions.manual_drafts import (
    ManualDraftNotFoundError,
    ManualDraftRepository,
)
from src.descriptions.parser import (
    ProductDescription,
    load_products as load_weber_products,
)
from src.descriptions.updater import (
    ProductUpdater,
    ProductUpdaterConfig,
)
from src.woocommerce import (
    load_products as load_woo_products,
)


DEFAULT_SOURCE_FILE = Path(
    "src/descriptions/weber_gas_grills.csv"
)

Q1200N_IMPORT_ID = "WEBERQ_1200N_BL"

SEPARATOR = "=" * 72


class PreviewError(RuntimeError):
    """Raised when a safe manual preview cannot be prepared."""


def build_manual_preview(
    *,
    product: ProductDescription,
    woo_products: Sequence[dict[str, Any]],
    orchestrator: GrillDescriptionOrchestrator,
) -> GrillDescriptionResult:
    """Run one manual description through the grill pipeline."""

    return orchestrator.process(
        product=product,
        woo_products=tuple(woo_products),
    )


def _find_source_product(
    *,
    products: Sequence[ProductDescription],
    import_id: str,
) -> ProductDescription:
    """Find exactly one Weber source product by import ID."""

    matches = [
        product
        for product in products
        if product.import_id == import_id
    ]

    if not matches:
        raise PreviewError(
            f"Weber produkts ar Import ID {import_id} netika atrasts."
        )

    if len(matches) > 1:
        raise PreviewError(
            f"Weber Import ID {import_id} nav unikāls."
        )

    return matches[0]


def _status_value(status: object) -> str:
    """Return an update status as human-readable text."""

    return str(getattr(status, "value", status))


def print_preview(
    result: GrillDescriptionResult,
) -> None:
    """Print the formatted description and each target's final payload."""

    formatted = result.formatted

    print(SEPARATOR)
    print("MANUAL GRILL DESCRIPTION PREVIEW")
    print(SEPARATOR)

    print(f"TITLE: {formatted.title}")

    print()
    print("SHORT DESCRIPTION")
    print("-" * 72)
    print(formatted.short_description)

    print()
    print("DESCRIPTION HTML")
    print("-" * 72)
    print(formatted.description_html)

    print()
    print("META DESCRIPTION")
    print("-" * 72)
    print(formatted.meta_description)

    print()
    print("WOOCOMMERCE TARGETS")
    print("-" * 72)

    for update in result.updates:
        print()
        print(f"SKU: {update.sku}")
        print(f"STATUS: {_status_value(update.status)}")

        payload = update.payload

        if not isinstance(payload, dict):
            print("PAYLOAD: nav pieejams")
            continue

        description = payload.get("description")

        if description is None:
            print(
                "DESCRIPTION: nav izmaiņu "
                "vai nav sagatavots"
            )
            continue

        print()
        print("FINAL DESCRIPTION HTML")
        print("-" * 72)
        print(description)

        print()
        print(
            "CONFIGURATION SECTION: "
            + (
                "YES"
                if "<h2>Komplektācija</h2>" in description
                else "NO"
            )
        )

    print()
    print(
        "QUALITY: "
        + (
            "PASSED"
            if result.quality.passed
            else "FAILED"
        )
    )

    print(SEPARATOR)


def run_manual_preview(
    *,
    import_id: str,
    source_file: Path = DEFAULT_SOURCE_FILE,
) -> int:
    """Run one manual Weber description in safe dry-run mode."""

    repository = ManualDraftRepository()

    # Validate the manual draft before loading WooCommerce.
    try:
        repository.get(import_id)
    except ManualDraftNotFoundError as exc:
        raise PreviewError(str(exc)) from exc

    products = load_weber_products(source_file)

    product = _find_source_product(
        products=products,
        import_id=import_id,
    )

    woo_products = load_woo_products(
        force_refresh=True,
    )

    products_by_sku = {
        str(woo_product.get("sku") or "").strip(): woo_product
        for woo_product in woo_products
        if str(woo_product.get("sku") or "").strip()
    }

    def product_loader(
        sku: str,
    ) -> dict[str, Any] | None:
        return products_by_sku.get(sku)

    def forbidden_writer(
        product_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raise AssertionError(
            "Preview režīmā WooCommerce rakstīšana nedrīkst notikt."
        )

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=product_loader,
        product_writer=forbidden_writer,
    )

    orchestrator = GrillDescriptionOrchestrator(
        translator=repository,
        updater=updater,
    )

    result = build_manual_preview(
        product=product,
        woo_products=woo_products,
        orchestrator=orchestrator,
    )

    print_preview(result)

    return 0


def run_q1200n_preview(
    *,
    source_file: Path = DEFAULT_SOURCE_FILE,
) -> int:
    """Preserve the existing Q1200N preview entry point."""

    return run_manual_preview(
        import_id=Q1200N_IMPORT_ID,
        source_file=source_file,
    )


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(
        description=(
            "Preview one manual Weber grill description "
            "without WooCommerce writes."
        )
    )
    parser.add_argument(
        "--import-id",
        default=Q1200N_IMPORT_ID,
        help="Weber source Import ID.",
    )

    args = parser.parse_args()

    try:
        return run_manual_preview(
            import_id=args.import_id,
        )
    except PreviewError as exc:
        print(f"Kļūda: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
