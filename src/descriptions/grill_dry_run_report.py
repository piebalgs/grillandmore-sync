"""Dry-run reporting for Weber grill description processing.

This module represents and collects the outcome of processing Weber
source descriptions before any live WooCommerce update is performed.

It does not perform matching, translation, quality checking,
or WooCommerce updates itself. Those responsibilities remain with
GrillDescriptionOrchestrator and its dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.descriptions.description_pipeline import PipelineQualityError
from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
    GrillTargetNotFoundError,
)
from src.descriptions.parser import ProductDescription
from src.descriptions.updater import UpdateStatus


class GrillDryRunStatus(str, Enum):
    """Overall processing outcome for one Weber source product."""

    READY = "ready"
    NO_TARGET = "no_target"
    QUALITY_FAILED = "quality_failed"


@dataclass(frozen=True, slots=True)
class GrillDryRunRow:
    """Dry-run report row for one Weber source product."""

    source_sku: str
    source_title: str
    status: GrillDryRunStatus
    target_skus: tuple[str, ...] = ()
    update_statuses: tuple[UpdateStatus, ...] = ()
    quality_passed: bool | None = None
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class GrillDryRunReport:
    """Collection of dry-run rows with summary helpers."""

    rows: tuple[GrillDryRunRow, ...]

    @property
    def total(self) -> int:
        """Return total number of source products in the report."""

        return len(self.rows)

    @property
    def ready_count(self) -> int:
        """Return number of successfully prepared source products."""

        return sum(
            row.status is GrillDryRunStatus.READY
            for row in self.rows
        )

    @property
    def no_target_count(self) -> int:
        """Return number of source products without Woo targets."""

        return sum(
            row.status is GrillDryRunStatus.NO_TARGET
            for row in self.rows
        )

    @property
    def quality_failed_count(self) -> int:
        """Return number of products that failed quality checks."""

        return sum(
            row.status is GrillDryRunStatus.QUALITY_FAILED
            for row in self.rows
        )

    @property
    def ready_rows(self) -> tuple[GrillDryRunRow, ...]:
        """Return rows ready for WooCommerce dry-run review."""

        return tuple(
            row
            for row in self.rows
            if row.status is GrillDryRunStatus.READY
        )

    @property
    def problem_rows(self) -> tuple[GrillDryRunRow, ...]:
        """Return rows requiring manual attention."""

        return tuple(
            row
            for row in self.rows
            if row.status is not GrillDryRunStatus.READY
        )


def build_grill_dry_run_report(
    *,
    products: Iterable[ProductDescription],
    woo_products: tuple[dict[str, Any], ...],
    orchestrator: GrillDescriptionOrchestrator,
) -> GrillDryRunReport:
    """Process Weber products and collect one dry-run row per source product.

    Expected per-product failures are converted into report rows so one
    unmatched or quality-failed product does not stop the complete run.
    Unexpected exceptions are intentionally not swallowed.
    """

    rows: list[GrillDryRunRow] = []

    for product in products:
        try:
            result = orchestrator.process(
                product=product,
                woo_products=woo_products,
            )

        except GrillTargetNotFoundError as error:
            rows.append(
                GrillDryRunRow(
                    source_sku=product.sku,
                    source_title=product.title,
                    status=GrillDryRunStatus.NO_TARGET,
                    error_message=str(error),
                )
            )
            continue

        except PipelineQualityError as error:
            rows.append(
                GrillDryRunRow(
                    source_sku=product.sku,
                    source_title=product.title,
                    status=GrillDryRunStatus.QUALITY_FAILED,
                    quality_passed=False,
                    error_message=str(error),
                )
            )
            continue

        rows.append(
            GrillDryRunRow(
                source_sku=product.sku,
                source_title=product.title,
                status=GrillDryRunStatus.READY,
                target_skus=tuple(
                    update.sku
                    for update in result.updates
                ),
                update_statuses=tuple(
                    update.status
                    for update in result.updates
                ),
                quality_passed=result.quality.passed,
            )
        )

    return GrillDryRunReport(
        rows=tuple(rows),
    )