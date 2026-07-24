"""Tests for quality_checker.py."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from src.descriptions.models import (
    FormattedProduct,
    GlossaryMatch,
    KnowledgeCategory,
    KnowledgeItem,
    ProductCategory,
    ProductContext,
    QualityCheck,
    QualityReport,
    SectionId,
    Severity,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.quality_checker import (
    DEFAULT_RULES,
    QualityChecker,
    QualityCheckerConfig,
    QualityCheckerError,
    format_quality_report,
)
from src.descriptions.knowledge_base import KnowledgeBase


# ----------------------------------------------------------------------
# Helper factories
# ----------------------------------------------------------------------


def make_product(**changes) -> FormattedProduct:
    values = {
        "sku": "ABC-123",
        "title": "Weber Genesis EP-335W",
        "short_description": (
            "<p>Augstas kvalitātes gāzes grils ikdienas lietošanai.</p>"
        ),
        "description_html": (
            "<p>"
            + " ".join(["Šis grils nodrošina vienmērīgu siltuma sadali."] * 30)
            + "</p>"
        ),
        "meta_description": (
            "Weber Genesis EP-335W gāzes grils ar vienmērīgu "
            "karstuma sadali un augstu kvalitāti."
        ),
        "search_keywords": (
            "Weber",
            "Genesis",
            "gāzes grils",
        ),
        "warnings": (),
        "metadata": {},
    }

    values.update(changes)

    return FormattedProduct(**values)


def make_draft(**changes) -> TranslationDraft:
    values = {
        "title": "Weber Genesis EP-335W",
        "introduction": (
            "Šis gāzes grils nodrošina vienmērīgu siltuma sadali un palīdz "
            "gatavot precīzāk."
        ),
        "benefits": (
            "Vienmērīga siltuma sadale.",
            "Ērta temperatūras kontrole.",
            "Augsta izturība.",
        ),
        "technologies": (
            "PureBlu degļu sistēma.",
        ),
        "suitability": (
            "Piemērots ģimenēm un regulārai grilēšanai."
        ),
        "specifications_summary": (
            "3 degļi, čuguna restes."
        ),
        "conclusion": (
            "Praktiska izvēle ikdienas lietošanai."
        ),
        "used_knowledge_keys": (
            "PureBlu",
        ),
        "warnings": (),
        "metadata": {},
    }

    values.update(changes)

    return TranslationDraft(**values)


def make_context(**changes) -> TranslationContext:
    product = ProductContext(
        sku="ABC-123",
        import_id="ABC-123",
        brand="Weber",
        product_name="Genesis EP-335W",
        category=ProductCategory.GAS_GRILL,
        glossary_terms=(
            GlossaryMatch(
                source="gas grill",
                target="gāzes grils",
            ),
        ),
        knowledge_keys=(
            "PureBlu",
        ),
        sections=(
            SectionId.INTRODUCTION,
            SectionId.BENEFITS,
            SectionId.TECHNOLOGIES,
            SectionId.SPECIFICATIONS,
        ),
        warnings=(),
        metadata={},
    )

    values = {
        "product": product,
        "source_language": "en",
        "target_language": "lv",
        "source_description": (
            "3 burner gas grill with PureBlu burner system."
        ),
        "source_sales_arguments": (),
        "source_benefits": (),
        "source_features": (),
        "source_specifications": {
            "burners": "3",
        },
        "translated_specifications": {
            "burners": (
                "Degļu skaits",
                "3",
            )
        },
        "style_instructions": "",
        "metadata": {},
    }

    values.update(changes)

    return TranslationContext(**values)


def make_checker(**changes) -> QualityChecker:
    config = QualityCheckerConfig(**changes)
    return QualityChecker(config=config)


# ----------------------------------------------------------------------
# QualityCheckerConfig
# ----------------------------------------------------------------------


def test_default_configuration_is_valid():
    config = QualityCheckerConfig()

    assert config.min_title_length == 5
    assert config.max_title_length == 180
    assert config.require_brand_in_title is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_title_length", -1),
        ("max_title_length", -1),
        ("min_short_description_words", -1),
        ("max_short_description_words", -1),
        ("min_meta_description_length", -1),
        ("max_meta_description_length", -1),
        ("min_search_keywords", -1),
        ("max_search_keywords", -1),
    ],
)
def test_negative_configuration_values_are_rejected(field, value):
    kwargs = {field: value}

    with pytest.raises(ValueError):
        QualityCheckerConfig(**kwargs)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        ("min_title_length", "max_title_length"),
        (
            "min_short_description_words",
            "max_short_description_words",
        ),
        (
            "min_meta_description_length",
            "max_meta_description_length",
        ),
        (
            "min_search_keywords",
            "max_search_keywords",
        ),
    ],
)
def test_invalid_ranges_are_rejected(minimum, maximum):
    kwargs = {
        minimum: 100,
        maximum: 10,
    }

    with pytest.raises(ValueError):
        QualityCheckerConfig(**kwargs)


@pytest.mark.parametrize(
    "field",
    [
        "min_title_length",
        "max_title_length",
        "min_short_description_words",
        "max_short_description_words",
        "min_meta_description_length",
        "max_meta_description_length",
        "min_search_keywords",
        "max_search_keywords",
    ],
)
def test_configuration_requires_integer_values(field):
    kwargs = {
        field: "abc",
    }

    with pytest.raises(TypeError):
        QualityCheckerConfig(**kwargs)


def test_checker_uses_default_rules():
    checker = QualityChecker()

    assert checker.rules == DEFAULT_RULES


def test_checker_exposes_configuration():
    checker = make_checker()

    assert isinstance(
        checker.config,
        QualityCheckerConfig,
    )


def test_checker_requires_unique_rule_codes():
    class Rule:
        code = "duplicate"

        def evaluate(self, _):
            return ()

    with pytest.raises(QualityCheckerError):
        QualityChecker(
            rules=(
                Rule(),
                Rule(),
            )
        )


def test_checker_requires_evaluate_method():
    class Rule:
        code = "broken"

    with pytest.raises(QualityCheckerError):
        QualityChecker(
            rules=(Rule(),)
        )
# ----------------------------------------------------------------------
# RequiredFieldsRule
# ----------------------------------------------------------------------


def test_required_fields_pass_for_complete_product():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(),
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert checks["required_fields.sku"].passed is True
    assert checks["required_fields.title"].passed is True
    assert checks["required_fields.short_description"].passed is True
    assert checks["required_fields.description_html"].passed is True
    assert checks["required_fields.meta_description"].passed is True


@pytest.mark.parametrize(
    ("field_name", "check_code"),
    [
        ("sku", "required_fields.sku"),
        ("title", "required_fields.title"),
        (
            "short_description",
            "required_fields.short_description",
        ),
        (
            "description_html",
            "required_fields.description_html",
        ),
        (
            "meta_description",
            "required_fields.meta_description",
        ),
    ],
)
def test_empty_required_field_fails(field_name, check_code):
    product = make_product(
        **{field_name: ""}
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == check_code
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR
    assert check.field_name == field_name


@pytest.mark.parametrize(
    "empty_value",
    [
        "",
        " ",
        "\n",
        "\t",
        "   \n\t   ",
    ],
)
def test_required_fields_treat_whitespace_as_empty(empty_value):
    product = make_product(
        title=empty_value,
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "required_fields.title"
    )

    assert check.passed is False


def test_meta_description_can_be_optional():
    checker = make_checker(
        require_meta_description=False,
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            meta_description="",
        ),
    )

    assert all(
        check.code != "required_fields.meta_description"
        for check in report.checks
    )


def test_required_field_failure_makes_report_fail():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            title="",
        ),
    )

    assert report.passed is False
    assert report.error_count >= 1


# ----------------------------------------------------------------------
# IdentityRule
# ----------------------------------------------------------------------


def test_identity_rule_passes_when_skus_match():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "identity.sku_match"
    )

    assert check.passed is True
    assert check.severity == Severity.ERROR
    assert check.field_name == "sku"


def test_identity_rule_fails_when_skus_differ():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            sku="XYZ-999",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "identity.sku_match"
    )

    assert check.passed is False
    assert "ABC-123" in check.message
    assert "XYZ-999" in check.message
    assert report.passed is False


def test_identity_rule_normalizes_outer_whitespace():
    context = make_context(
        product=replace(
            make_context().product,
            sku="  ABC-123  ",
        )
    )

    product = make_product(
        sku="ABC-123",
    )

    report = QualityChecker().check(
        context=context,
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "identity.sku_match"
    )

    assert check.passed is True


def test_identity_rule_is_case_sensitive():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            sku="abc-123",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "identity.sku_match"
    )

    assert check.passed is False


def test_identity_rule_fails_for_empty_context_sku():
    context = make_context(
        product=replace(
            make_context().product,
            sku="",
        )
    )

    report = QualityChecker().check(
        context=context,
        draft=make_draft(),
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "identity.sku_match"
    )

    assert check.passed is False


# ----------------------------------------------------------------------
# TitleRule
# ----------------------------------------------------------------------


def test_title_rule_passes_for_valid_title():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(),
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert checks["title.length"].passed is True
    assert checks["title.brand"].passed is True


def test_title_rule_fails_when_title_is_too_short():
    checker = make_checker(
        min_title_length=10,
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            title="Weber",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.length"
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR
    assert check.field_name == "title"


def test_title_rule_fails_when_title_is_too_long():
    checker = make_checker(
        max_title_length=20,
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            title="Weber Genesis EP-335W ļoti garš nosaukums",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.length"
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR


def test_title_minimum_boundary_passes():
    checker = make_checker(
        min_title_length=5,
        max_title_length=20,
    )

    report = checker.check(
        context=make_context(
            product=replace(
                make_context().product,
                brand="",
            )
        ),
        draft=make_draft(),
        product=make_product(
            title="ABCDE",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.length"
    )

    assert check.passed is True


def test_title_maximum_boundary_passes():
    checker = make_checker(
        min_title_length=5,
        max_title_length=10,
    )

    report = checker.check(
        context=make_context(
            product=replace(
                make_context().product,
                brand="",
            )
        ),
        draft=make_draft(),
        product=make_product(
            title="ABCDEFGHIJ",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.length"
    )

    assert check.passed is True


def test_title_brand_check_is_case_insensitive():
    product = make_product(
        title="WEBER Genesis EP-335W",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.brand"
    )

    assert check.passed is True


def test_title_brand_check_fails_when_brand_is_missing():
    product = make_product(
        title="Genesis EP-335W gāzes grils",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.brand"
    )

    assert check.passed is False
    assert check.severity == Severity.WARNING
    assert "Weber" in check.message


def test_title_brand_check_can_be_disabled():
    checker = make_checker(
        require_brand_in_title=False,
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            title="Genesis EP-335W gāzes grils",
        ),
    )

    assert all(
        check.code != "title.brand"
        for check in report.checks
    )


def test_empty_brand_does_not_fail_title_check():
    context = make_context(
        product=replace(
            make_context().product,
            brand="",
        )
    )

    report = QualityChecker().check(
        context=context,
        draft=make_draft(),
        product=make_product(
            title="Genesis EP-335W gāzes grils",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.brand"
    )

    assert check.passed is True


def test_title_length_counts_normalized_outer_whitespace():
    checker = make_checker(
        min_title_length=5,
        max_title_length=5,
        require_brand_in_title=False,
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            title="   ABCDE   ",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "title.length"
    )

    assert check.passed is True
    # ----------------------------------------------------------------------
# DescriptionLengthRule
# ----------------------------------------------------------------------


def test_description_length_passes_for_valid_description():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is True
    assert check.severity == Severity.WARNING
    assert check.field_name == "description_html"


def test_description_length_fails_when_too_short():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            description_html="<p>Īss apraksts.</p>",
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is False
    assert "120" in check.message


def test_description_length_fails_when_too_long():
    description = "<p>" + " ".join(["grils"] * 651) + "</p>"

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            description_html=description,
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is False
    assert "651" in check.message
    assert "650" in check.message


def test_description_minimum_boundary_passes():
    description = "<p>" + " ".join(["grils"] * 120) + "</p>"

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            description_html=description,
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is True


def test_description_maximum_boundary_passes():
    description = "<p>" + " ".join(["grils"] * 650) + "</p>"

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            description_html=description,
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is True


def test_description_word_count_ignores_html_tags():
    description = (
        "<h2>Produkta apraksts</h2>"
        "<p>"
        + " ".join(["grils"] * 120)
        + "</p>"
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(
            description_html=description,
        ),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "description_length"
    )

    assert check.passed is True


# ----------------------------------------------------------------------
# ShortDescriptionRule
# ----------------------------------------------------------------------


def test_short_description_passes_for_valid_length():
    product = make_product(
        short_description=(
            "<p>Weber gāzes grils palīdz gatavot ērti un precīzi.</p>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is True


def test_short_description_fails_when_too_short():
    product = make_product(
        short_description="<p>Labs grils.</p>",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is False
    assert check.severity == Severity.WARNING


def test_short_description_fails_when_too_long():
    product = make_product(
        short_description=(
            "<p>" + " ".join(["grils"] * 81) + "</p>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is False


def test_short_description_minimum_boundary_passes():
    checker = make_checker(
        min_short_description_words=8,
        max_short_description_words=20,
    )

    product = make_product(
        short_description=(
            "<p>Viens divi trīs četri pieci seši septiņi astoņi.</p>"
        ),
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is True


def test_short_description_maximum_boundary_passes():
    checker = make_checker(
        min_short_description_words=1,
        max_short_description_words=8,
    )

    product = make_product(
        short_description=(
            "<p>Viens divi trīs četri pieci seši septiņi astoņi.</p>"
        ),
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is True


def test_short_description_word_count_ignores_html():
    checker = make_checker(
        min_short_description_words=4,
        max_short_description_words=4,
    )

    product = make_product(
        short_description="<p><strong>Viens divi</strong> trīs četri.</p>",
    )

    report = checker.check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "short_description.length"
    )

    assert check.passed is True


# ----------------------------------------------------------------------
# HTMLRule
# ----------------------------------------------------------------------


def test_html_rule_passes_for_allowed_tags():
    product = make_product(
        description_html=(
            "<h2>Produkta apraksts</h2>"
            "<p>Apraksta teksts.</p>"
            "<ul>"
            "<li><strong>Pirmais ieguvums</strong></li>"
            "<li><em>Otrais ieguvums</em></li>"
            "</ul>"
            "<table>"
            "<tbody>"
            "<tr><th>Degļi</th><td>3</td></tr>"
            "</tbody>"
            "</table>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert checks["html.allowed_tags"].passed is True
    assert checks["html.structure"].passed is True


@pytest.mark.parametrize(
    "tag",
    [
        "script",
        "iframe",
        "div",
        "span",
        "style",
        "a",
        "img",
    ],
)
def test_html_rule_rejects_disallowed_tags(tag):
    product = make_product(
        description_html=(
            f"<{tag}>Neatļauts saturs</{tag}>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "html.allowed_tags"
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR
    assert f"<{tag}>" in check.message


def test_html_rule_reports_multiple_disallowed_tags():
    product = make_product(
        description_html=(
            "<div><span>Saturs</span></div>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "html.allowed_tags"
    )

    assert check.passed is False
    assert "<div>" in check.message
    assert "<span>" in check.message


def test_html_rule_detects_missing_closing_tag():
    product = make_product(
        description_html="<p>Neaizvērta rindkopa",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "html.structure"
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR
    assert "<p>" in check.message


def test_html_rule_detects_unmatched_closing_tag():
    product = make_product(
        description_html="Teksts</p>",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "html.structure"
    )

    assert check.passed is False
    assert "</p>" in check.message


def test_html_rule_detects_wrong_nesting():
    product = make_product(
        description_html="<p><strong>Teksts</p></strong>",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "html.structure"
    )

    assert check.passed is False
    assert "Nepareiza tagu secība" in check.message


def test_html_rule_accepts_empty_allowed_elements():
    product = make_product(
        description_html="<p></p><ul></ul>",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert checks["html.allowed_tags"].passed is True
    assert checks["html.structure"].passed is True


def test_html_rule_is_case_insensitive_for_tags():
    product = make_product(
        description_html="<P>Teksts</P>",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=product,
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert checks["html.allowed_tags"].passed is True
    assert checks["html.structure"].passed is True


# ----------------------------------------------------------------------
# MarketingLanguageRule
# ----------------------------------------------------------------------


def test_marketing_language_passes_for_clean_text():
    report = QualityChecker().check(
        context=make_context(),
        draft=make_draft(),
        product=make_product(),
    )

    checks = {
        check.code: check
        for check in report.checks
    }

    assert (
        checks["marketing_language.forbidden_phrases"].passed
        is True
    )
    assert (
        checks["marketing_language.discouraged_words"].passed
        is True
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "pasaulē labākais",
        "vislabākais",
        "nepārspējams",
        "revolucionārs",
        "unikāls risinājums",
        "ideāls ikvienam",
        "perfekta izvēle",
        "obligāti nepieciešams",
        "bez konkurences",
        "neticams",
        "fantastisks",
        "ekskluzīvs piedāvājums",
        "mainīs jūsu dzīvi",
    ],
)
def test_marketing_language_rejects_forbidden_phrases(phrase):
    draft = make_draft(
        introduction=f"Šis ir {phrase} grils.",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code
        == "marketing_language.forbidden_phrases"
    )

    assert check.passed is False
    assert check.severity == Severity.ERROR
    assert phrase in check.message


def test_marketing_language_is_case_insensitive():
    draft = make_draft(
        introduction="Šis ir PASAULĒ LABĀKAIS grils.",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code
        == "marketing_language.forbidden_phrases"
    )

    assert check.passed is False


@pytest.mark.parametrize(
    "word",
    [
        "vienkārši",
        "protams",
        "acīmredzami",
        "neticami",
        "ārkārtīgi",
        "absolūti",
    ],
)
def test_marketing_language_warns_for_discouraged_words(word):
    draft = make_draft(
        introduction=f"Šis grils {word} palīdz gatavot.",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code
        == "marketing_language.discouraged_words"
    )

    assert check.passed is False
    assert check.severity == Severity.WARNING
    assert word in check.message


def test_discouraged_word_check_can_be_disabled():
    checker = make_checker(
        check_discouraged_words=False,
    )

    draft = make_draft(
        introduction="Šis grils vienkārši palīdz gatavot.",
    )

    report = checker.check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    assert all(
        check.code
        != "marketing_language.discouraged_words"
        for check in report.checks
    )


def test_marketing_language_checks_all_draft_sections():
    draft = make_draft(
        conclusion="Šī ir perfekta izvēle.",
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code
        == "marketing_language.forbidden_phrases"
    )

    assert check.passed is False


# ----------------------------------------------------------------------
# SentenceLengthRule
# ----------------------------------------------------------------------


def test_sentence_length_passes_for_normal_sentences():
    draft = make_draft(
        introduction=(
            "Šis grils nodrošina vienmērīgu siltumu. "
            "Tas palīdz gatavot precīzi."
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "sentence_length"
    )

    assert check.passed is True


def test_sentence_length_warns_for_overlong_sentence():
    long_sentence = " ".join(
        [f"vārds{index}" for index in range(29)]
    ) + "."

    draft = make_draft(
        introduction=long_sentence,
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "sentence_length"
    )

    assert check.passed is False
    assert check.severity == Severity.WARNING
    assert "1" in check.message
    assert long_sentence in check.message


def test_sentence_length_maximum_boundary_passes():
    sentence = " ".join(
        [f"vārds{index}" for index in range(28)]
    ) + "."

    draft = make_draft(
        title="Weber grils.",
        introduction=sentence,
    )

    product = make_product(
        description_html=(
            "<p>Īss apraksts. Vēl viens īss teikums.</p>"
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=product,
    )

    check = next(
        item
        for item in report.checks
        if item.code == "sentence_length"
    )

    assert check.passed is True


def test_sentence_length_reports_number_of_long_sentences():
    long_sentence_one = " ".join(
        [f"pirmais{index}" for index in range(29)]
    ) + "."
    long_sentence_two = " ".join(
        [f"otrais{index}" for index in range(30)]
    ) + "."

    draft = make_draft(
        introduction=(
            long_sentence_one
            + " "
            + long_sentence_two
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "sentence_length"
    )

    assert check.passed is False
    assert "2" in check.message
    assert long_sentence_one in check.message


def test_sentence_length_checks_benefit_items():
    long_benefit = " ".join(
        [f"ieguvums{index}" for index in range(29)]
    ) + "."

    draft = make_draft(
        benefits=(
            long_benefit,
            "Ērta lietošana.",
            "Izturīga konstrukcija.",
        ),
    )

    report = QualityChecker().check(
        context=make_context(),
        draft=draft,
        product=make_product(),
    )

    check = next(
        item
        for item in report.checks
        if item.code == "sentence_length"
    )

    assert check.passed is False