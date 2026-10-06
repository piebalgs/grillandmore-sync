"""Tests for manual grill-description preview output."""

from __future__ import annotations

from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionResult,
)
from src.descriptions.models import (
    FormattedProduct,
    ProductCategory,
    ProductContext,
    QualityReport,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.updater import (
    UpdateResult,
    UpdateStatus,
)
from preview_manual_grill_description import print_preview


def test_print_preview_shows_complete_q1200n_dry_run(
    capsys,
) -> None:
    """Preview shows content, quality result, and all Woo targets."""

    context = TranslationContext(
        product=ProductContext(
            sku="WEBERQ_1200N_BL",
            import_id="WEBERQ_1200N_BL",
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
        title="Weber Q 1200N gāzes grils",
        introduction="Kompakts Weber Q 1200N gāzes grils.",
    )

    formatted = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q 1200N gāzes grils",
        short_description=(
            "<p>Kompakts Weber Q 1200N gāzes grils.</p>"
        ),
        description_html=(
            "<p>Kompakts Weber Q 1200N gāzes grils.</p>"
            "<ul><li>Līdz 9 burgeriem.</li></ul>"
        ),
        meta_description=(
            "Weber Q 1200N kompakts gāzes grils ikdienas grilēšanai."
        ),
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

    result = GrillDescriptionResult(
        context=context,
        draft=draft,
        formatted=formatted,
        quality=quality,
        updates=updates,
    )

    print_preview(result)

    output = capsys.readouterr().out

    assert "Weber Q 1200N gāzes grils" in output
    assert "SHORT DESCRIPTION" in output
    assert formatted.short_description in output
    assert "DESCRIPTION HTML" in output
    assert formatted.description_html in output
    assert "META DESCRIPTION" in output
    assert formatted.meta_description in output
    assert "1501071" in output
    assert "1501086" in output
    assert "dry_run" in output
    assert "QUALITY: PASSED" in output