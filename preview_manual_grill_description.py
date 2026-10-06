"""Preview manually approved grill descriptions without WooCommerce writes."""

from __future__ import annotations

from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionResult,
)


SEPARATOR = "=" * 72


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