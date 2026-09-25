"""Tests for Weber grill description dry-run reports."""

from __future__ import annotations

from src.descriptions.description_pipeline import PipelineQualityError
from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionResult,
    GrillTargetNotFoundError,
)
from src.descriptions.grill_dry_run_report import (
    GrillDryRunReport,
    GrillDryRunRow,
    GrillDryRunStatus,
    build_grill_dry_run_report,
)
from src.descriptions.models import (
    FormattedProduct,
    ProductCategory,
    ProductContext,
    QualityCheck,
    QualityReport,
    Severity,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.parser import ProductDescription
from src.descriptions.updater import (
    UpdateResult,
    UpdateStatus,
)


def test_report_summarizes_all_product_outcomes():
    rows = (
        GrillDryRunRow(
            source_sku="WEBERQ_1200N_BL",
            source_title="Weber Q 1200N Gas Grill",
            status=GrillDryRunStatus.READY,
            target_skus=("1501071", "1501086"),
            update_statuses=(
                UpdateStatus.DRY_RUN,
                UpdateStatus.DRY_RUN,
            ),
            quality_passed=True,
        ),
        GrillDryRunRow(
            source_sku="SUMMIT_FS38X_S",
            source_title="Summit FS38X S Gas Grill",
            status=GrillDryRunStatus.NO_TARGET,
        ),
        GrillDryRunRow(
            source_sku="TEST_FAILED",
            source_title="Test Grill",
            status=GrillDryRunStatus.QUALITY_FAILED,
            target_skus=("9999999",),
            quality_passed=False,
            error_message="Kvalitātes pārbaude neizturēta.",
        ),
    )

    report = GrillDryRunReport(rows=rows)

    assert report.total == 3
    assert report.ready_count == 1
    assert report.no_target_count == 1
    assert report.quality_failed_count == 1

    assert report.ready_rows == (rows[0],)
    assert report.problem_rows == (
        rows[1],
        rows[2],
    )


def test_build_report_continues_after_expected_product_failures():
    ready_product = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBER_Q1200N",
        title="Weber Q 1200N Gas Grill",
        source_description="Weber Q1200N Gas Grill.",
    )

    no_target_product = ProductDescription(
        sku="SUMMIT_FS38X_S",
        import_id="SUMMIT_FS38X_S",
        title="Summit FS38X S Gas Grill",
        source_description="Summit FS38X S Gas Grill.",
    )

    quality_failed_product = ProductDescription(
        sku="TEST_FAILED",
        import_id="TEST_FAILED",
        title="Test Grill",
        source_description="Test Grill.",
    )

    context = TranslationContext(
        product=ProductContext(
            sku="WEBERQ_1200N_BL",
            import_id="WEBER_Q1200N",
            brand="Weber",
            product_name="Weber Q 1200N Gas Grill",
            category=ProductCategory.GAS_GRILL,
            sections=(),
        ),
        source_language="en",
        target_language="lv",
        source_description="Weber Q1200N Gas Grill.",
    )

    draft = TranslationDraft(
        title="Weber Q1200N gāzes grils",
        introduction="Kompakts Weber gāzes grils.",
    )

    formatted = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N gāzes grils",
        short_description="<p>Kompakts Weber gāzes grils.</p>",
        description_html="<p>Kompakts Weber gāzes grils.</p>",
    )

    quality = QualityReport.from_checks(
        sku="WEBERQ_1200N_BL",
        checks=(),
    )

    updates = (
        UpdateResult(
            sku="1501071",
            status=UpdateStatus.DRY_RUN,
        ),
        UpdateResult(
            sku="1501086",
            status=UpdateStatus.DRY_RUN,
        ),
    )

    ready_result = GrillDescriptionResult(
        context=context,
        draft=draft,
        formatted=formatted,
        quality=quality,
        updates=updates,
    )

    failed_quality = QualityReport.from_checks(
        sku="TEST_FAILED",
        checks=(
            QualityCheck(
                code="test.failure",
                message="Kvalitātes pārbaude neizturēta.",
                severity=Severity.ERROR,
                passed=False,
            ),
        ),
    )

    class Orchestrator:
        def __init__(self):
            self.calls = []

        def process(self, *, product, woo_products):
            self.calls.append(product.sku)

            if product.sku == "SUMMIT_FS38X_S":
                raise GrillTargetNotFoundError(
                    "Produktam Summit FS38X S Gas Grill "
                    "nav atrasts atbilstošs WooCommerce mērķis."
                )

            if product.sku == "TEST_FAILED":
                raise PipelineQualityError(
                    "Produkta TEST_FAILED apraksts "
                    "neizturēja kvalitātes pārbaudi.",
                    quality_report=failed_quality,
                )

            return ready_result

    orchestrator = Orchestrator()

    report = build_grill_dry_run_report(
        products=(
            ready_product,
            no_target_product,
            quality_failed_product,
        ),
        woo_products=(),
        orchestrator=orchestrator,
    )

    assert orchestrator.calls == [
        "WEBERQ_1200N_BL",
        "SUMMIT_FS38X_S",
        "TEST_FAILED",
    ]

    assert report.total == 3
    assert report.ready_count == 1
    assert report.no_target_count == 1
    assert report.quality_failed_count == 1

    ready_row = report.rows[0]
    assert ready_row.source_sku == "WEBERQ_1200N_BL"
    assert ready_row.status is GrillDryRunStatus.READY
    assert ready_row.target_skus == (
        "1501071",
        "1501086",
    )
    assert ready_row.update_statuses == (
        UpdateStatus.DRY_RUN,
        UpdateStatus.DRY_RUN,
    )
    assert ready_row.quality_passed is True

    no_target_row = report.rows[1]
    assert no_target_row.source_sku == "SUMMIT_FS38X_S"
    assert no_target_row.status is GrillDryRunStatus.NO_TARGET
    assert no_target_row.target_skus == ()
    assert no_target_row.quality_passed is None
    assert "Summit FS38X S" in no_target_row.error_message

    failed_row = report.rows[2]
    assert failed_row.source_sku == "TEST_FAILED"
    assert failed_row.status is GrillDryRunStatus.QUALITY_FAILED
    assert failed_row.quality_passed is False
    assert "neizturēja kvalitātes pārbaudi" in failed_row.error_message