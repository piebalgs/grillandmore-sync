"""Preview manually approved grill descriptions without WooCommerce writes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
    GrillDescriptionResult,
)
from src.descriptions.manual_drafts import ManualDraftRepository
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
    """Run one manually approved description through the grill pipeline."""

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
    """Print the complete formatted result of one grill description."""

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
        print(
            f"{update.sku}: "
            f"{_status_value(update.status)}"
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


def run_q1200n_preview(
    *,
    source_file: Path = DEFAULT_SOURCE_FILE,
) -> int:
    """Run the approved Q1200N description through a safe dry run."""

    products = load_weber_products(source_file)

    product = _find_source_product(
        products=products,
        import_id=Q1200N_IMPORT_ID,
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
        translator=ManualDraftRepository(),
        updater=updater,
    )

    result = build_manual_preview(
        product=product,
        woo_products=woo_products,
        orchestrator=orchestrator,
    )

    print_preview(result)

    return 0


def main() -> int:
    """CLI entry point."""

    try:
        return run_q1200n_preview()
    except PreviewError as exc:
        print(f"Kļūda: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())