"""Run the Weber gas-grill description workflow in safe dry-run mode.

The runner loads all Weber gas-grill source descriptions and the current
WooCommerce catalog, generates Latvian descriptions through the configured
OpenAI client, performs quality checks, and prepares WooCommerce updates.

WooCommerce writes remain disabled by the description factory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.core.config import (
    ConfigurationError,
    settings,
)
from src.descriptions.factory import (
    create_grill_description_orchestrator,
)
from src.descriptions.grill_dry_run_report import (
    GrillDryRunReport,
    GrillDryRunStatus,
    build_grill_dry_run_report,
)
from src.descriptions.parser import (
    DescriptionParseError,
    ProductDescription,
    load_products as load_weber_products,
)
from src.woocommerce import (
    load_products as load_woo_products,
)


DEFAULT_SOURCE_FILE = Path(
    "src/descriptions/weber_gas_grills.csv"
)

SEPARATOR = "=" * 72


class CLIError(RuntimeError):
    """Raised for expected command-line runner errors."""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Palaiž Weber gāzes grilu latviešu aprakstu "
            "ģenerēšanu drošā WooCommerce DRY RUN režīmā."
        )
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_FILE,
        help=(
            "Ceļš uz Weber gāzes grilu CSV failu. "
            f"Noklusējums: {DEFAULT_SOURCE_FILE}"
        ),
    )

    return parser.parse_args()


def load_source_products(
    path: Path,
) -> list[ProductDescription]:
    """Load Weber source products and convert parser errors to CLI errors."""

    source = path.expanduser()

    if not source.is_file():
        raise CLIError(
            f"CSV fails nav atrasts: {source}"
        )

    try:
        products = load_weber_products(source)
    except (
        FileNotFoundError,
        DescriptionParseError,
    ) as exc:
        raise CLIError(str(exc)) from exc

    if not products:
        raise CLIError(
            f"CSV failā nav atrasts neviens produkts: {source}"
        )

    return products


def _format_target_skus(
    target_skus: tuple[str, ...],
) -> str:
    """Return target SKUs in a compact human-readable form."""

    if not target_skus:
        return "-"

    return ", ".join(target_skus)


def _format_update_statuses(
    statuses: tuple[object, ...],
) -> str:
    """Return update statuses in a compact human-readable form."""

    if not statuses:
        return "-"

    values: list[str] = []

    for status in statuses:
        value = getattr(status, "value", status)
        values.append(str(value))

    return ", ".join(values)


def print_report(
    report: GrillDryRunReport,
) -> None:
    """Print the complete human-readable dry-run report."""

    print(SEPARATOR)
    print("WEBER GRILL DESCRIPTION DRY RUN")
    print(SEPARATOR)
    print(f"Kopā:              {report.total}")
    print(f"Gatavi:             {report.ready_count}")
    print(f"Bez mērķa:          {report.no_target_count}")
    print(
        "Kvalitāte neizieta: "
        f"{report.quality_failed_count}"
    )
    print(SEPARATOR)

    for index, row in enumerate(
        report.rows,
        start=1,
    ):
        print()
        print(
            f"{index}. "
            f"{row.source_title or row.source_sku}"
        )
        print("-" * 72)
        print(
            f"Avota SKU:          "
            f"{row.source_sku or '-'}"
        )
        print(
            f"Statuss:            "
            f"{row.status.value}"
        )
        print(
            "WooCommerce SKU:    "
            f"{_format_target_skus(row.target_skus)}"
        )
        print(
            "Update statuss:      "
            f"{_format_update_statuses(row.update_statuses)}"
        )

        if row.quality_passed is not None:
            print(
                "Kvalitāte:          "
                + (
                    "PASSED"
                    if row.quality_passed
                    else "FAILED"
                )
            )

        if row.error_message:
            print(
                f"Ziņojums:           "
                f"{row.error_message}"
            )

    print()
    print(SEPARATOR)
    print("KOPSAVILKUMS")
    print(SEPARATOR)
    print(f"Kopā:              {report.total}")
    print(f"Gatavi:             {report.ready_count}")
    print(f"Bez mērķa:          {report.no_target_count}")
    print(
        "Kvalitāte neizieta: "
        f"{report.quality_failed_count}"
    )

    if report.problem_rows:
        print("Rezultāts:          NEEDS REVIEW")
    else:
        print("Rezultāts:          READY")

    print(SEPARATOR)


def run(
    args: argparse.Namespace,
) -> int:
    """Run the complete Weber grill description dry run."""

    products = load_source_products(
        args.source,
    )

    woo_products = load_woo_products(
        force_refresh=True,
    )

    orchestrator = (
        create_grill_description_orchestrator(
            settings=settings,
        )
    )

    report = build_grill_dry_run_report(
        products=products,
        woo_products=tuple(woo_products),
        orchestrator=orchestrator,
    )

    print_report(report)

    if any(
        row.status is not GrillDryRunStatus.READY
        for row in report.rows
    ):
        return 1

    return 0


def main() -> int:
    """CLI entry point."""

    args = parse_args()

    try:
        return run(args)

    except (
        CLIError,
        ConfigurationError,
    ) as exc:
        print(
            f"Kļūda: {exc}",
            file=sys.stderr,
        )
        return 2

    except KeyboardInterrupt:
        print(
            "\nDarbību pārtrauca lietotājs.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())