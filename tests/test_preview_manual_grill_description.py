"""Tests for manual grill-description preview output."""

from __future__ import annotations

from unittest.mock import patch

from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
    GrillDescriptionResult,
)
from src.descriptions.manual_drafts import ManualDraftRepository
from src.descriptions.models import (
    FormattedProduct,
    ProductCategory,
    ProductContext,
    QualityReport,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.parser import ProductDescription
from src.descriptions.updater import (
    ProductUpdater,
    ProductUpdaterConfig,
    UpdateResult,
    UpdateStatus,
)
from preview_manual_grill_description import (
    build_manual_preview,
    print_preview,
    run_q1200n_preview,
)


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


def test_build_manual_preview_runs_q1200n_pipeline_without_writes() -> None:
    """Q1200N manual draft runs through the real pipeline in dry-run mode."""

    source = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBERQ_1200N_BL",
        title="Weber Q 1200N Gas Grill",
        source_description=(
            "The high-efficiency burner and porcelain-enameled cast-iron "
            "grates ensure your food cooks evenly, delivering delicious "
            "results every time. With 46% more space under the high-dome "
            "lid than previous models, you get a large roasting capacity."
        ),
        sales_arguments=(
            "Compact and lightweight design fits nicely in small spaces",
            "Large grilling surface accommodates up to 9 burgers",
            "High-dome lid allows more capacity for larger roasts",
            "High-efficiency burner delivers fast, consistent high heat",
            "Porcelain-enameled cast-iron grates retain heat for searing",
            "Side tables add surface space, detach and stow within the cradle",
            "Front-facing grease tray enables quick and easy grease disposal",
            "Built-in lid thermometer displays temperature clearly",
            "Upgraded electronic ignition lights quickly with a single press",
        ),
        specifications={
            "grate_size": "49 x 38 cm",
            "grate_shape": "SQUARE",
            "color": "Black",
            "dimensions_open_lid": "64 x 56 x 105 cm",
            "dimensions_closed_lid": "38 x 46 x 105 cm",
            "net_weight": "11 kg",
            "guarantee": "5_L",
            "hamburger_capacity": "6",
        },
    )

    woo_products = (
        {
            "id": 201,
            "sku": "1501071",
            "name": "Gāzes grils Weber Q1200N",
            "description": "",
            "short_description": "",
            "meta_data": [],
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 202,
            "sku": "1501086",
            "name": "Gāzes grils Weber Q1200N ar statīvu",
            "description": "",
            "short_description": "",
            "meta_data": [],
            "categories": [{"id": 422}, {"id": 247}],
        },
    )

    products_by_sku = {
        product["sku"]: product
        for product in woo_products
    }

    writer_calls = []

    def forbidden_writer(product_id, payload):
        writer_calls.append((product_id, payload))
        raise AssertionError(
            "Preview režīmā WooCommerce rakstīšana nedrīkst notikt."
        )

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=lambda sku: products_by_sku.get(sku),
        product_writer=forbidden_writer,
    )

    orchestrator = GrillDescriptionOrchestrator(
        translator=ManualDraftRepository(),
        updater=updater,
    )

    result = build_manual_preview(
        product=source,
        woo_products=woo_products,
        orchestrator=orchestrator,
    )

    assert result.draft.title == "Weber Q 1200N gāzes grils"
    assert "līdz 9 burgeriem" in result.draft.introduction
    assert "hamburger_capacity" not in result.draft.specifications_summary

    assert result.quality.passed is True

    assert tuple(
        update.sku
        for update in result.updates
    ) == (
        "1501071",
        "1501086",
    )

    assert all(
        update.status is UpdateStatus.DRY_RUN
        for update in result.updates
    )

    assert result.formatted.short_description
    assert result.formatted.description_html
    assert result.formatted.meta_description

    assert writer_calls == []


def test_run_q1200n_preview_loads_real_source_and_stays_dry_run(
    tmp_path,
    capsys,
) -> None:
    """Runner selects Q1200N and prints a safe manual dry-run preview."""

    source_file = tmp_path / "weber.csv"
    source_file.write_text(
        "placeholder",
        encoding="utf-8",
    )

    source = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBERQ_1200N_BL",
        title="Weber Q 1200N Gas Grill",
        source_description=(
            "The high-efficiency burner and porcelain-enameled cast-iron "
            "grates ensure your food cooks evenly, delivering delicious "
            "results every time. With 46% more space under the high-dome "
            "lid than previous models, you get a large roasting capacity."
        ),
        sales_arguments=(
            "Compact and lightweight design fits nicely in small spaces",
            "Large grilling surface accommodates up to 9 burgers",
            "High-dome lid allows more capacity for larger roasts",
            "High-efficiency burner delivers fast, consistent high heat",
            "Porcelain-enameled cast-iron grates retain heat for searing",
            "Side tables add surface space, detach and stow within the cradle",
            "Front-facing grease tray enables quick and easy grease disposal",
            "Built-in lid thermometer displays temperature clearly",
            "Upgraded electronic ignition lights quickly with a single press",
        ),
        specifications={
            "grate_size": "49 x 38 cm",
            "grate_shape": "SQUARE",
            "color": "Black",
            "dimensions_open_lid": "64 x 56 x 105 cm",
            "dimensions_closed_lid": "38 x 46 x 105 cm",
            "net_weight": "11 kg",
            "guarantee": "5_L",
            "hamburger_capacity": "6",
        },
    )

    woo_products = [
        {
            "id": 201,
            "sku": "1501071",
            "name": "Gāzes grils Weber Q1200N",
            "description": "",
            "short_description": "",
            "meta_data": [],
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 202,
            "sku": "1501086",
            "name": "Gāzes grils Weber Q1200N ar statīvu",
            "description": "",
            "short_description": "",
            "meta_data": [],
            "categories": [{"id": 422}, {"id": 247}],
        },
    ]

    with (
        patch(
            "preview_manual_grill_description.load_weber_products",
            return_value=[source],
        ) as source_loader,
        patch(
            "preview_manual_grill_description.load_woo_products",
            return_value=woo_products,
        ) as woo_loader,
    ):
        exit_code = run_q1200n_preview(
            source_file=source_file,
        )

    assert exit_code == 0

    source_loader.assert_called_once_with(source_file)
    woo_loader.assert_called_once_with(
        force_refresh=True,
    )

    output = capsys.readouterr().out

    assert "Weber Q 1200N gāzes grils" in output
    assert "līdz 9 burgeriem" in output
    assert "1501071: dry_run" in output
    assert "1501086: dry_run" in output
    assert "QUALITY: PASSED" in output