"""Tests for description_pipeline.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.descriptions.description_pipeline import (
    DescriptionPipeline,
    PipelineConfig,
    PipelineQualityError,
    PipelineResult,
)
from src.descriptions.models import (
    FormattedProduct,
    ProductCategory,
    ProductContext,
    QualityCheck,
    QualityReport,
    SectionId,
    Severity,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.parser import ProductDescription


# ----------------------------------------------------------------------
# Test data factories
# ----------------------------------------------------------------------


def make_source_product() -> ProductDescription:
    return ProductDescription(
        sku="ABC-123",
        import_id="import-1",
        title="Weber Genesis EP-335W",
        source_description=(
            "A versatile gas grill with an efficient burner system."
        ),
        sales_arguments=(
            "Even heat distribution",
            "Durable construction",
        ),
        specifications={
            "barbecue_type": "GAS",
            "guarantee": "10",
        },
    )


def make_context() -> TranslationContext:
    product = ProductContext(
        sku="ABC-123",
        import_id="import-1",
        brand="Weber",
        product_name="Weber Genesis EP-335W",
        category=ProductCategory.GAS_GRILL,
        sections=(
            SectionId.INTRODUCTION,
            SectionId.BENEFITS,
            SectionId.TECHNOLOGIES,
            SectionId.SUITABILITY,
            SectionId.SPECIFICATIONS,
        ),
    )

    return TranslationContext(
        product=product,
        source_language="en",
        target_language="lv",
        source_description=(
            "A versatile gas grill with an efficient burner system."
        ),
        source_sales_arguments=(
            "Even heat distribution",
            "Durable construction",
        ),
        source_specifications={
            "barbecue_type": "GAS",
            "guarantee": "10",
        },
        translated_specifications={
            "barbecue_type": (
                "Grila veids",
                "Gāzes grils",
            ),
            "guarantee": (
                "Garantija",
                "10 gadi",
            ),
        },
        style_instructions=(
            "Raksti skaidri, profesionāli un tehniski precīzi."
        ),
    )


def make_draft() -> TranslationDraft:
    return TranslationDraft(
        title="Weber Genesis EP-335W gāzes grils",
        introduction=(
            "Weber Genesis EP-335W ir daudzpusīgs gāzes grils "
            "regulārai gatavošanai ārā."
        ),
        benefits=(
            "Vienmērīga karstuma sadale.",
            "Ērta temperatūras regulēšana.",
            "Izturīga konstrukcija.",
        ),
        technologies=(
            "Efektīva degļu sistēma palīdz uzturēt vienmērīgu karstumu.",
        ),
        suitability=(
            "Piemērots ģimenēm un regulārai grilēšanai."
        ),
        specifications_summary=(
            "Gāzes grils ar 10 gadu garantiju."
        ),
        conclusion=(
            "Praktiska izvēle daudzveidīgai gatavošanai ārā."
        ),
    )


def make_formatted_product() -> FormattedProduct:
    return FormattedProduct(
        sku="ABC-123",
        title="Weber Genesis EP-335W gāzes grils",
        short_description=(
            "<p>Daudzpusīgs gāzes grils regulārai "
            "gatavošanai ārā.</p>"
        ),
        description_html=(
            "<h2>Weber Genesis EP-335W</h2>"
            "<p>Daudzpusīgs gāzes grils regulārai "
            "gatavošanai ārā.</p>"
            "<h3>Galvenie ieguvumi</h3>"
            "<ul>"
            "<li>Vienmērīga karstuma sadale.</li>"
            "<li>Ērta temperatūras regulēšana.</li>"
            "<li>Izturīga konstrukcija.</li>"
            "</ul>"
        ),
        meta_description=(
            "Weber Genesis EP-335W gāzes grils ar vienmērīgu "
            "karstuma sadali un izturīgu konstrukciju."
        ),
        search_keywords=(
            "Weber",
            "Genesis",
            "gāzes grils",
        ),
    )


def make_quality_report(
    *,
    passed: bool = True,
) -> QualityReport:
    if passed:
        checks = (
            QualityCheck(
                code="test.pass",
                message="Kvalitātes pārbaude izturēta.",
                severity=Severity.ERROR,
                passed=True,
            ),
        )
    else:
        checks = (
            QualityCheck(
                code="test.failure",
                message="Atrasta kvalitātes kļūda.",
                severity=Severity.ERROR,
                passed=False,
                field_name="description_html",
            ),
        )

    return QualityReport.from_checks(
        sku="ABC-123",
        checks=checks,
    )


def make_update_result(
    *,
    success: bool = True,
):
    """Return a minimal updater-compatible result for orchestration tests."""

    return SimpleNamespace(
        success=success,
        sku="ABC-123",
        action="updated" if success else "failed",
    )


# ----------------------------------------------------------------------
# Stub components
# ----------------------------------------------------------------------


class StubContextBuilder:
    def __init__(
        self,
        *,
        result: TranslationContext | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = result or make_context()
        self.error = error
        self.events = events
        self.calls: list[ProductDescription] = []

    def build(
        self,
        product: ProductDescription,
    ) -> TranslationContext:
        self.calls.append(product)

        if self.events is not None:
            self.events.append("context")

        if self.error is not None:
            raise self.error

        return self.result


class StubTranslator:
    def __init__(
        self,
        *,
        result: TranslationDraft | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = result or make_draft()
        self.error = error
        self.events = events
        self.calls: list[TranslationContext] = []

    def translate(
        self,
        context: TranslationContext,
    ) -> TranslationDraft:
        self.calls.append(context)

        if self.events is not None:
            self.events.append("translator")

        if self.error is not None:
            raise self.error

        return self.result


class StubFormatter:
    def __init__(
        self,
        *,
        result: FormattedProduct | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = result or make_formatted_product()
        self.error = error
        self.events = events
        self.calls: list[
            tuple[TranslationContext, TranslationDraft]
        ] = []

    def format(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
    ) -> FormattedProduct:
        self.calls.append(
            (
                context,
                draft,
            )
        )

        if self.events is not None:
            self.events.append("formatter")

        if self.error is not None:
            raise self.error

        return self.result


class StubQualityChecker:
    def __init__(
        self,
        *,
        result: QualityReport | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = result or make_quality_report()
        self.error = error
        self.events = events
        self.calls: list[
            tuple[
                TranslationContext,
                TranslationDraft,
                FormattedProduct,
            ]
        ] = []

    def check(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
        product: FormattedProduct,
    ) -> QualityReport:
        self.calls.append(
            (
                context,
                draft,
                product,
            )
        )

        if self.events is not None:
            self.events.append("quality")

        if self.error is not None:
            raise self.error

        return self.result


class StubUpdater:
    def __init__(
        self,
        *,
        result=None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = (
            result
            if result is not None
            else make_update_result()
        )
        self.error = error
        self.events = events
        self.calls: list[
            tuple[FormattedProduct, QualityReport]
        ] = []

    def update(
        self,
        *,
        product: FormattedProduct,
        quality_report: QualityReport,
    ):
        self.calls.append(
            (
                product,
                quality_report,
            )
        )

        if self.events is not None:
            self.events.append("updater")

        if self.error is not None:
            raise self.error

        return self.result


def make_pipeline(
    *,
    context_builder=None,
    translator=None,
    formatter=None,
    quality_checker=None,
    updater=None,
    config=None,
) -> DescriptionPipeline:
    return DescriptionPipeline(
        context_builder=(
            context_builder
            if context_builder is not None
            else StubContextBuilder()
        ),
        translator=(
            translator
            if translator is not None
            else StubTranslator()
        ),
        formatter=(
            formatter
            if formatter is not None
            else StubFormatter()
        ),
        quality_checker=(
            quality_checker
            if quality_checker is not None
            else StubQualityChecker()
        ),
        updater=(
            updater
            if updater is not None
            else StubUpdater()
        ),
        config=config,
    )


# ----------------------------------------------------------------------
# PipelineConfig
# ----------------------------------------------------------------------


def test_pipeline_config_defaults_to_strict_quality_gate():
    config = PipelineConfig()

    assert config.fail_on_quality_errors is True


@pytest.mark.parametrize(
    "invalid_value",
    [
        1,
        0,
        "true",
        None,
        [],
    ],
)
def test_pipeline_config_requires_boolean(
    invalid_value,
):
    with pytest.raises(
        TypeError,
        match="fail_on_quality_errors",
    ):
        PipelineConfig(
            fail_on_quality_errors=invalid_value,
        )


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------


def test_translator_is_required():
    with pytest.raises(
        TypeError,
        match="translator",
    ):
        DescriptionPipeline(
            translator=None,
        )


def test_injected_components_are_preserved():
    context_builder = StubContextBuilder()
    translator = StubTranslator()
    formatter = StubFormatter()
    quality_checker = StubQualityChecker()
    updater = StubUpdater()
    config = PipelineConfig(
        fail_on_quality_errors=False,
    )

    pipeline = DescriptionPipeline(
        context_builder=context_builder,
        translator=translator,
        formatter=formatter,
        quality_checker=quality_checker,
        updater=updater,
        config=config,
    )

    assert pipeline.context_builder is context_builder
    assert pipeline.translator is translator
    assert pipeline.formatter is formatter
    assert pipeline.quality_checker is quality_checker
    assert pipeline.updater is updater
    assert pipeline.config is config


# ----------------------------------------------------------------------
# Successful orchestration
# ----------------------------------------------------------------------


def test_process_returns_pipeline_result():
    result = make_pipeline().process(
        make_source_product()
    )

    assert isinstance(
        result,
        PipelineResult,
    )


def test_components_are_called_in_correct_order():
    events: list[str] = []

    pipeline = make_pipeline(
        context_builder=StubContextBuilder(
            events=events,
        ),
        translator=StubTranslator(
            events=events,
        ),
        formatter=StubFormatter(
            events=events,
        ),
        quality_checker=StubQualityChecker(
            events=events,
        ),
        updater=StubUpdater(
            events=events,
        ),
    )

    pipeline.process(
        make_source_product()
    )

    assert events == [
        "context",
        "translator",
        "formatter",
        "quality",
        "updater",
    ]


def test_source_product_is_passed_to_context_builder():
    product = make_source_product()
    context_builder = StubContextBuilder()

    make_pipeline(
        context_builder=context_builder,
    ).process(product)

    assert context_builder.calls == [
        product,
    ]


def test_context_is_passed_unchanged_to_translator():
    context = make_context()
    context_builder = StubContextBuilder(
        result=context,
    )
    translator = StubTranslator()

    make_pipeline(
        context_builder=context_builder,
        translator=translator,
    ).process(
        make_source_product()
    )

    assert translator.calls == [
        context,
    ]


def test_context_and_draft_are_passed_unchanged_to_formatter():
    context = make_context()
    draft = make_draft()
    formatter = StubFormatter()

    make_pipeline(
        context_builder=StubContextBuilder(
            result=context,
        ),
        translator=StubTranslator(
            result=draft,
        ),
        formatter=formatter,
    ).process(
        make_source_product()
    )

    assert formatter.calls == [
        (
            context,
            draft,
        ),
    ]


def test_quality_checker_receives_all_pipeline_objects():
    context = make_context()
    draft = make_draft()
    formatted = make_formatted_product()
    quality_checker = StubQualityChecker()

    make_pipeline(
        context_builder=StubContextBuilder(
            result=context,
        ),
        translator=StubTranslator(
            result=draft,
        ),
        formatter=StubFormatter(
            result=formatted,
        ),
        quality_checker=quality_checker,
    ).process(
        make_source_product()
    )

    assert quality_checker.calls == [
        (
            context,
            draft,
            formatted,
        ),
    ]


def test_updater_receives_formatted_product_and_quality_report():
    formatted = make_formatted_product()
    quality = make_quality_report()
    updater = StubUpdater()

    make_pipeline(
        formatter=StubFormatter(
            result=formatted,
        ),
        quality_checker=StubQualityChecker(
            result=quality,
        ),
        updater=updater,
    ).process(
        make_source_product()
    )

    assert updater.calls == [
        (
            formatted,
            quality,
        ),
    ]


def test_result_contains_all_intermediate_objects():
    context = make_context()
    draft = make_draft()
    formatted = make_formatted_product()
    quality = make_quality_report()
    update = make_update_result()

    result = make_pipeline(
        context_builder=StubContextBuilder(
            result=context,
        ),
        translator=StubTranslator(
            result=draft,
        ),
        formatter=StubFormatter(
            result=formatted,
        ),
        quality_checker=StubQualityChecker(
            result=quality,
        ),
        updater=StubUpdater(
            result=update,
        ),
    ).process(
        make_source_product()
    )

    assert result.context is context
    assert result.draft is draft
    assert result.formatted is formatted
    assert result.quality is quality
    assert result.update is update


def test_result_success_is_true_when_quality_and_update_succeed():
    result = make_pipeline().process(
        make_source_product()
    )

    assert result.success is True


def test_result_sku_comes_from_formatted_product():
    result = make_pipeline().process(
        make_source_product()
    )

    assert result.sku == "ABC-123"


def test_result_success_is_false_when_update_fails():
    result = make_pipeline(
        updater=StubUpdater(
            result=make_update_result(
                success=False,
            )
        )
    ).process(
        make_source_product()
    )

    assert result.success is False


# ----------------------------------------------------------------------
# Quality gate
# ----------------------------------------------------------------------


def test_failed_quality_report_stops_pipeline():
    quality = make_quality_report(
        passed=False,
    )
    updater = StubUpdater()

    pipeline = make_pipeline(
        quality_checker=StubQualityChecker(
            result=quality,
        ),
        updater=updater,
    )

    with pytest.raises(
        PipelineQualityError,
        match="ABC-123",
    ):
        pipeline.process(
            make_source_product()
        )

    assert updater.calls == []


def test_quality_error_contains_quality_report():
    quality = make_quality_report(
        passed=False,
    )

    pipeline = make_pipeline(
        quality_checker=StubQualityChecker(
            result=quality,
        ),
    )

    with pytest.raises(
        PipelineQualityError,
    ) as error_info:
        pipeline.process(
            make_source_product()
        )

    assert error_info.value.quality_report is quality


def test_quality_failure_can_be_forwarded_to_updater():
    quality = make_quality_report(
        passed=False,
    )
    updater = StubUpdater(
        result=make_update_result(
            success=False,
        )
    )

    pipeline = make_pipeline(
        quality_checker=StubQualityChecker(
            result=quality,
        ),
        updater=updater,
        config=PipelineConfig(
            fail_on_quality_errors=False,
        ),
    )

    result = pipeline.process(
        make_source_product()
    )

    assert updater.calls == [
        (
            make_formatted_product(),
            quality,
        ),
    ]
    assert result.quality is quality
    assert result.success is False


# ----------------------------------------------------------------------
# Invalid input
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_product",
    [
        None,
        {},
        "ABC-123",
        object(),
    ],
)
def test_process_requires_product_description(
    invalid_product,
):
    with pytest.raises(
        TypeError,
        match="ProductDescription",
    ):
        make_pipeline().process(
            invalid_product,
        )


# ----------------------------------------------------------------------
# Exception propagation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "component_name",
        "expected_events",
    ),
    [
        (
            "context",
            [
                "context",
            ],
        ),
        (
            "translator",
            [
                "context",
                "translator",
            ],
        ),
        (
            "formatter",
            [
                "context",
                "translator",
                "formatter",
            ],
        ),
        (
            "quality",
            [
                "context",
                "translator",
                "formatter",
                "quality",
            ],
        ),
        (
            "updater",
            [
                "context",
                "translator",
                "formatter",
                "quality",
                "updater",
            ],
        ),
    ],
)
def test_component_exceptions_are_propagated_unchanged(
    component_name,
    expected_events,
):
    events: list[str] = []
    expected_error = RuntimeError(
        f"{component_name} failure"
    )

    context_builder = StubContextBuilder(
        events=events,
        error=(
            expected_error
            if component_name == "context"
            else None
        ),
    )
    translator = StubTranslator(
        events=events,
        error=(
            expected_error
            if component_name == "translator"
            else None
        ),
    )
    formatter = StubFormatter(
        events=events,
        error=(
            expected_error
            if component_name == "formatter"
            else None
        ),
    )
    quality_checker = StubQualityChecker(
        events=events,
        error=(
            expected_error
            if component_name == "quality"
            else None
        ),
    )
    updater = StubUpdater(
        events=events,
        error=(
            expected_error
            if component_name == "updater"
            else None
        ),
    )

    pipeline = make_pipeline(
        context_builder=context_builder,
        translator=translator,
        formatter=formatter,
        quality_checker=quality_checker,
        updater=updater,
    )

    with pytest.raises(
        RuntimeError,
    ) as error_info:
        pipeline.process(
            make_source_product()
        )

    assert error_info.value is expected_error
    assert events == expected_events

