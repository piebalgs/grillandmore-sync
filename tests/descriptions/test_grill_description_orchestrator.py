"""Tests for multi-target Weber grill description orchestration."""

from __future__ import annotations

import pytest

from src.descriptions.description_pipeline import PipelineQualityError
from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
    GrillTargetNotFoundError,
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
    ProductUpdater,
    ProductUpdaterConfig,
    UpdateStatus,
)


def test_q1200n_is_generated_once_and_planned_for_both_woo_skus():
    source = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBER_Q1200N",
        title="Weber Q 1200N Gas Grill",
        source_description="Weber Q1200N Gas Grill.",
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

    class ContextBuilder:
        def __init__(self):
            self.calls = 0

        def build(self, product):
            self.calls += 1
            return context

    class Translator:
        def __init__(self):
            self.calls = 0

        def translate(self, translation_context):
            self.calls += 1
            return draft

    class Formatter:
        def __init__(self):
            self.calls = 0

        def format(self, *, context, draft):
            self.calls += 1
            return formatted

    class QualityChecker:
        def __init__(self):
            self.calls = 0

        def check(self, *, context, draft, product):
            self.calls += 1
            return quality

    products_by_sku = {
        product["sku"]: product
        for product in woo_products
    }

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=lambda sku: products_by_sku.get(sku),
        product_writer=lambda product_id, payload: None,
    )

    context_builder = ContextBuilder()
    translator = Translator()
    formatter = Formatter()
    quality_checker = QualityChecker()

    orchestrator = GrillDescriptionOrchestrator(
        context_builder=context_builder,
        translator=translator,
        formatter=formatter,
        quality_checker=quality_checker,
        updater=updater,
    )

    result = orchestrator.process(
        product=source,
        woo_products=woo_products,
    )

    assert context_builder.calls == 1
    assert translator.calls == 1
    assert formatter.calls == 1
    assert quality_checker.calls == 1

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


def test_failed_quality_stops_before_any_target_update():
    source = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBER_Q1200N",
        title="Weber Q 1200N Gas Grill",
        source_description="Weber Q1200N Gas Grill.",
    )

    woo_products = (
        {
            "id": 201,
            "sku": "1501071",
            "name": "Gāzes grils Weber Q1200N",
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 202,
            "sku": "1501086",
            "name": "Gāzes grils Weber Q1200N ar statīvu",
            "categories": [{"id": 422}, {"id": 247}],
        },
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
        checks=(
            QualityCheck(
                code="test.failure",
                message="Kvalitātes pārbaude neizturēta.",
                severity=Severity.ERROR,
                passed=False,
            ),
        ),
    )

    class ContextBuilder:
        def build(self, product):
            return context

    class Translator:
        def translate(self, translation_context):
            return draft

    class Formatter:
        def format(self, *, context, draft):
            return formatted

    class QualityChecker:
        def check(self, *, context, draft, product):
            return quality

    updater_calls = []

    class Updater:
        def update(self, *, product, quality_report):
            updater_calls.append(product.sku)
            raise AssertionError(
                "Updater nedrīkst tikt izsaukts."
            )

    orchestrator = GrillDescriptionOrchestrator(
        context_builder=ContextBuilder(),
        translator=Translator(),
        formatter=Formatter(),
        quality_checker=QualityChecker(),
        updater=Updater(),
    )

    with pytest.raises(
        PipelineQualityError,
    ) as error_info:
        orchestrator.process(
            product=source,
            woo_products=woo_products,
        )

    assert error_info.value.quality_report is quality
    assert updater_calls == []


def test_missing_woo_target_stops_before_description_generation():
    source = ProductDescription(
        sku="SUMMIT_FS38X_S",
        import_id="SUMMIT_FS38X_S",
        title="Summit FS38X S Gas Grill",
        source_description="Summit FS38X S Gas Grill.",
    )

    woo_products = (
        {
            "id": 301,
            "sku": "1500178",
            "name": "Gāzes grils Summit FS38X E Smart",
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 302,
            "sku": "1500099",
            "name": "Gāzes grils Summit FS38 S, nerūsējošais tērauds",
            "categories": [{"id": 422}, {"id": 247}],
        },
    )

    class ContextBuilder:
        def __init__(self):
            self.calls = 0

        def build(self, product):
            self.calls += 1
            raise AssertionError(
                "ContextBuilder nedrīkst tikt izsaukts."
            )

    class Translator:
        def __init__(self):
            self.calls = 0

        def translate(self, context):
            self.calls += 1
            raise AssertionError(
                "Translator nedrīkst tikt izsaukts."
            )

    context_builder = ContextBuilder()
    translator = Translator()

    orchestrator = GrillDescriptionOrchestrator(
        context_builder=context_builder,
        translator=translator,
    )

    with pytest.raises(
    GrillTargetNotFoundError,
    match="Summit FS38X S",
    ):
        orchestrator.process(
            product=source,
            woo_products=woo_products,
        )

    assert context_builder.calls == 0
    assert translator.calls == 0