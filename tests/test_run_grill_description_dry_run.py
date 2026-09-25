"""Tests for the Weber grill description dry-run CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.descriptions.grill_dry_run_report import (
    GrillDryRunReport,
    GrillDryRunRow,
    GrillDryRunStatus,
)
from src.descriptions.updater import UpdateStatus

from run_grill_description_dry_run import (
    CLIError,
    DEFAULT_SOURCE_FILE,
    load_source_products,
    print_report,
    run,
)


def _make_args(
    *,
    source: Path,
) -> argparse.Namespace:
    """Return CLI arguments for runner tests."""

    return argparse.Namespace(
        source=source,
    )


def _make_report() -> GrillDryRunReport:
    """Return a representative dry-run report."""

    return GrillDryRunReport(
        rows=(
            GrillDryRunRow(
                source_sku="1501071",
                source_title="Q1200N Gas Grill",
                status=GrillDryRunStatus.READY,
                target_skus=(
                    "1501071",
                    "1501086",
                ),
                update_statuses=(
                    UpdateStatus.DRY_RUN,
                    UpdateStatus.DRY_RUN,
                ),
                quality_passed=True,
            ),
            GrillDryRunRow(
                source_sku="1509999",
                source_title="Summit FS38X S Gas Grill",
                status=GrillDryRunStatus.NO_TARGET,
                error_message="WooCommerce mērķis nav atrasts.",
            ),
        )
    )


def test_default_source_file_points_to_weber_gas_export() -> None:
    """Runner uses the project Weber gas-grill source by default."""

    assert DEFAULT_SOURCE_FILE == Path(
        "src/descriptions/weber_gas_grills.csv"
    )


def test_load_source_products_rejects_missing_file(
    tmp_path: Path,
) -> None:
    """Missing source files are reported as CLI errors."""

    missing = tmp_path / "missing.csv"

    with pytest.raises(
        CLIError,
        match="CSV fails nav atrasts",
    ):
        load_source_products(missing)


def test_print_report_shows_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human-readable output contains the important summary."""

    print_report(_make_report())

    output = capsys.readouterr().out

    assert "WEBER GRILL DESCRIPTION DRY RUN" in output
    assert "Kopā:" in output
    assert "2" in output
    assert "Gatavi:" in output
    assert "1" in output
    assert "Bez mērķa:" in output
    assert "Q1200N Gas Grill" in output
    assert "1501071, 1501086" in output
    assert "Summit FS38X S Gas Grill" in output


def test_run_builds_report_without_live_woo_writes(
    tmp_path: Path,
) -> None:
    """Runner loads both catalogs and delegates processing to dry run."""

    source = tmp_path / "weber.csv"
    source.write_text(
        "placeholder",
        encoding="utf-8",
    )

    product = Mock()
    product.sku = "WEBER-1"
    product.title = "Q1200N Gas Grill"

    woo_products = [
        {
            "id": 1,
            "sku": "1501071",
            "name": "Q1200N",
        }
    ]

    orchestrator = Mock()
    report = _make_report()

    with (
        patch(
            "run_grill_description_dry_run.load_source_products",
            return_value=[product],
        ) as source_loader,
        patch(
            "run_grill_description_dry_run.load_woo_products",
            return_value=woo_products,
        ) as woo_loader,
        patch(
            "run_grill_description_dry_run.create_grill_description_orchestrator",
            return_value=orchestrator,
        ) as factory,
        patch(
            "run_grill_description_dry_run.build_grill_dry_run_report",
            return_value=report,
        ) as report_builder,
        patch(
            "run_grill_description_dry_run.print_report",
        ) as report_printer,
    ):
        exit_code = run(
            _make_args(
                source=source,
            )
        )

    assert exit_code == 1

    source_loader.assert_called_once_with(source)
    woo_loader.assert_called_once_with(
        force_refresh=True,
    )
    factory.assert_called_once()
    report_builder.assert_called_once_with(
        products=[product],
        woo_products=tuple(woo_products),
        orchestrator=orchestrator,
    )
    report_printer.assert_called_once_with(report)


def test_run_returns_zero_when_all_products_are_ready(
    tmp_path: Path,
) -> None:
    """A completely ready dry run exits successfully."""

    source = tmp_path / "weber.csv"
    source.write_text(
        "placeholder",
        encoding="utf-8",
    )

    product = Mock()

    report = GrillDryRunReport(
        rows=(
            GrillDryRunRow(
                source_sku="WEBER-1",
                source_title="Q1200N Gas Grill",
                status=GrillDryRunStatus.READY,
                target_skus=("1501071",),
                update_statuses=(
                    UpdateStatus.DRY_RUN,
                ),
                quality_passed=True,
            ),
        )
    )

    with (
        patch(
            "run_grill_description_dry_run.load_source_products",
            return_value=[product],
        ),
        patch(
            "run_grill_description_dry_run.load_woo_products",
            return_value=[],
        ),
        patch(
            "run_grill_description_dry_run.create_grill_description_orchestrator",
            return_value=Mock(),
        ),
        patch(
            "run_grill_description_dry_run.build_grill_dry_run_report",
            return_value=report,
        ),
        patch(
            "run_grill_description_dry_run.print_report",
        ),
    ):
        exit_code = run(
            _make_args(
                source=source,
            )
        )

    assert exit_code == 0