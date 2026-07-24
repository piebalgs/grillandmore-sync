from __future__ import annotations

from types import MappingProxyType

import pytest

from src.descriptions.formatter import (
    FormatterConfigurationError,
    FormatterConfig,
    FormatterInputError,
    HTMLBuilder,
    ProductFormatter,
    _truncate_at_word_boundary,
)
from src.descriptions.models import (
    GlossaryMatch,
    ProductCategory,
    ProductContext,
    SectionId,
    TranslationContext,
    TranslationDraft,
)


def make_context(
    *,
    sku: str = "18412",
    category: ProductCategory = ProductCategory.GAS_GRILL,
    sections: tuple[SectionId, ...] | None = None,
    glossary_terms: tuple[GlossaryMatch, ...] = (
        GlossaryMatch(
            source="Flavorizer Bars",
            target="Flavorizer aromatizējošās plāksnes",
        ),
        GlossaryMatch(
            source="GS4",
            target="GS4",
        ),
    ),
    knowledge_keys: tuple[str, ...] = (
        "gs4",
        "porcelain_enamel",
    ),
    metadata: dict | None = None,
) -> TranslationContext:
    if sections is None:
        sections = (
            SectionId.INTRODUCTION,
            SectionId.BENEFITS,
            SectionId.TECHNOLOGIES,
            SectionId.SUITABILITY,
            SectionId.SPECIFICATIONS,
        )

    return TranslationContext(
        product=ProductContext(
            sku=sku,
            import_id="import-18412",
            brand="Weber",
            product_name="Weber Spirit E-325",
            category=category,
            glossary_terms=glossary_terms,
            knowledge_keys=knowledge_keys,
            sections=sections,
        ),
        source_description="Source description",
        metadata=metadata or {},
    )


def make_draft(**overrides) -> TranslationDraft:
    values = {
        "title": "Weber Spirit E-325 gāzes grils",
        "introduction": (
            "Jaudīgs un daudzpusīgs grils ģimenes maltītēm."
        ),
        "benefits": (
            "Ātri un vienmērīgi uzkarst.",
            "Viegli tīrāms pēc gatavošanas.",
        ),
        "technologies": (
            "GS4 grilēšanas sistēma.",
            "Flavorizer aromatizējošās plāksnes.",
        ),
        "suitability": (
            "Piemērots ikdienas gatavošanai uz terases."
        ),
        "specifications_summary": (
            "Trīs degļi un čuguna režģis."
        ),
        "conclusion": (
            "Droša izvēle gardām maltītēm."
        ),
        "used_knowledge_keys": ("gs4",),
        "warnings": ("Pārbaudīt izmērus.",),
        "metadata": {
            "model": "fake-model",
            "request_id": "req-1",
        },
    }

    values.update(overrides)

    return TranslationDraft(**values)


# ---------------------------------------------------------------------------
# HTMLBuilder
# ---------------------------------------------------------------------------


def test_html_builder_paragraph():
    builder = HTMLBuilder()

    builder.paragraph("Ievads")

    assert builder.html == "<p>Ievads</p>"


def test_html_builder_heading():
    builder = HTMLBuilder()

    builder.heading("Priekšrocības")

    assert builder.html == "<h2>Priekšrocības</h2>"


def test_html_builder_custom_heading_level():
    builder = HTMLBuilder(heading_level=3)

    builder.heading("Priekšrocības")

    assert builder.html == "<h3>Priekšrocības</h3>"


def test_html_builder_unordered_list():
    builder = HTMLBuilder()

    builder.unordered_list(
        (
            "Pirmais",
            "Otrais",
        )
    )

    assert builder.html == (
        "<ul>\n"
        "  <li>Pirmais</li>\n"
        "  <li>Otrais</li>\n"
        "</ul>"
    )


def test_html_builder_combines_blocks():
    builder = HTMLBuilder()

    builder.paragraph("Ievads")
    builder.heading("Priekšrocības")
    builder.unordered_list(("Pirmais",))

    assert builder.html == (
        "<p>Ievads</p>\n\n"
        "<h2>Priekšrocības</h2>\n\n"
        "<ul>\n"
        "  <li>Pirmais</li>\n"
        "</ul>"
    )


def test_html_builder_escapes_paragraph():
    builder = HTMLBuilder()

    builder.paragraph(
        '<script>alert("x")</script> & droši'
    )

    assert "<script>" not in builder.html
    assert "&lt;script&gt;" in builder.html
    assert "&amp; droši" in builder.html


def test_html_builder_escapes_heading():
    builder = HTMLBuilder()

    builder.heading("A < B")

    assert builder.html == "<h2>A &lt; B</h2>"


def test_html_builder_escapes_list_items():
    builder = HTMLBuilder()

    builder.unordered_list(
        ("<b>trekns</b>",)
    )

    assert "<b>trekns</b>" not in builder.html
    assert "&lt;b&gt;trekns&lt;/b&gt;" in builder.html


def test_html_builder_ignores_empty_values():
    builder = HTMLBuilder()

    builder.paragraph(" ")
    builder.heading("")
    builder.unordered_list(
        (
            "",
            "   ",
        )
    )

    assert builder.html == ""


def test_html_builder_normalizes_whitespace():
    builder = HTMLBuilder()

    builder.paragraph(
        "  Ērts\n\n grils\u00a0ģimenei.  "
    )

    assert builder.html == (
        "<p>Ērts grils ģimenei.</p>"
    )


@pytest.mark.parametrize(
    "heading_level",
    (
        0,
        7,
    ),
)
def test_html_builder_rejects_invalid_heading_level(
    heading_level,
):
    with pytest.raises(
        FormatterConfigurationError
    ):
        HTMLBuilder(
            heading_level=heading_level
        )


# ---------------------------------------------------------------------------
# FormatterConfig
# ---------------------------------------------------------------------------


def test_formatter_config_defaults():
    config = FormatterConfig()

    assert config.heading_level == 2
    assert config.max_short_description_length == 320
    assert config.max_meta_description_length == 155
    assert config.include_conclusion is True
    assert config.include_empty_sections is False
    assert config.include_product_name_keyword is True


@pytest.mark.parametrize(
    "heading_level",
    (
        0,
        7,
    ),
)
def test_config_rejects_invalid_heading_level(
    heading_level,
):
    with pytest.raises(
        FormatterConfigurationError
    ):
        FormatterConfig(
            heading_level=heading_level
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "max_short_description_length",
        "max_meta_description_length",
    ),
)
def test_config_rejects_non_positive_lengths(
    field_name,
):
    with pytest.raises(
        FormatterConfigurationError
    ):
        FormatterConfig(
            **{field_name: 0}
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "benefits_heading",
        "technologies_heading",
        "suitability_heading",
        "specifications_heading",
    ),
)
def test_config_rejects_empty_heading(
    field_name,
):
    with pytest.raises(
        FormatterConfigurationError
    ):
        FormatterConfig(
            **{field_name: " "}
        )


def test_custom_formatter_config():
    config = FormatterConfig(
        heading_level=4,
        max_short_description_length=200,
        max_meta_description_length=140,
        include_conclusion=False,
        include_empty_sections=True,
        include_product_name_keyword=False,
        benefits_heading="Ieguvumi",
    )

    assert config.heading_level == 4
    assert config.max_short_description_length == 200
    assert config.max_meta_description_length == 140
    assert config.include_conclusion is False
    assert config.include_empty_sections is True
    assert config.include_product_name_keyword is False
    assert config.benefits_heading == "Ieguvumi"


# ---------------------------------------------------------------------------
# ProductFormatter pamata darbība
# ---------------------------------------------------------------------------


def test_format_returns_complete_product():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert formatted.sku == "18412"
    assert formatted.title == (
        "Weber Spirit E-325 gāzes grils"
    )
    assert formatted.short_description
    assert formatted.description_html
    assert formatted.meta_description
    assert formatted.search_keywords


def test_full_html_output():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert formatted.description_html == (
        "<p>Jaudīgs un daudzpusīgs grils "
        "ģimenes maltītēm.</p>\n\n"
        "<h2>Galvenās priekšrocības</h2>\n\n"
        "<ul>\n"
        "  <li>Ātri un vienmērīgi uzkarst.</li>\n"
        "  <li>Viegli tīrāms pēc gatavošanas.</li>\n"
        "</ul>\n\n"
        "<h2>Tehnoloģijas</h2>\n\n"
        "<ul>\n"
        "  <li>GS4 grilēšanas sistēma.</li>\n"
        "  <li>Flavorizer aromatizējošās "
        "plāksnes.</li>\n"
        "</ul>\n\n"
        "<h2>Piemērots</h2>\n\n"
        "<p>Piemērots ikdienas gatavošanai "
        "uz terases.</p>\n\n"
        "<h2>Tehniskā informācija</h2>\n\n"
        "<p>Trīs degļi un čuguna režģis.</p>\n\n"
        "<p>Droša izvēle gardām maltītēm.</p>"
    )


def test_formatter_uses_custom_heading_level():
    formatter = ProductFormatter(
        FormatterConfig(
            heading_level=4
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(),
    )

    assert (
        "<h4>Galvenās priekšrocības</h4>"
        in formatted.description_html
    )
    assert "<h2>" not in formatted.description_html


def test_formatter_uses_custom_headings():
    formatter = ProductFormatter(
        FormatterConfig(
            benefits_heading="Ieguvumi",
            technologies_heading=(
                "Iebūvētās tehnoloģijas"
            ),
            suitability_heading=(
                "Kam paredzēts"
            ),
            specifications_heading=(
                "Specifikācija"
            ),
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "<h2>Ieguvumi</h2>" in (
        formatted.description_html
    )
    assert (
        "<h2>Iebūvētās tehnoloģijas</h2>"
        in formatted.description_html
    )
    assert "<h2>Kam paredzēts</h2>" in (
        formatted.description_html
    )
    assert "<h2>Specifikācija</h2>" in (
        formatted.description_html
    )


def test_disabled_sections_are_not_rendered():
    context = make_context(
        sections=(
            SectionId.INTRODUCTION,
            SectionId.BENEFITS,
        )
    )

    formatted = ProductFormatter().format(
        context=context,
        draft=make_draft(),
    )

    assert "Galvenās priekšrocības" in (
        formatted.description_html
    )
    assert "Tehnoloģijas" not in (
        formatted.description_html
    )
    assert "Piemērots" not in (
        formatted.description_html
    )
    assert "Tehniskā informācija" not in (
        formatted.description_html
    )


@pytest.mark.parametrize(
    (
        "field_name",
        "empty_value",
        "heading",
    ),
    (
        (
            "benefits",
            (),
            "Galvenās priekšrocības",
        ),
        (
            "technologies",
            (),
            "Tehnoloģijas",
        ),
        (
            "suitability",
            "",
            "Piemērots",
        ),
        (
            "specifications_summary",
            "",
            "Tehniskā informācija",
        ),
    ),
)
def test_empty_section_is_omitted(
    field_name,
    empty_value,
    heading,
):
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            **{field_name: empty_value}
        ),
    )

    assert heading not in (
        formatted.description_html
    )


def test_empty_sections_can_keep_headings():
    formatter = ProductFormatter(
        FormatterConfig(
            include_empty_sections=True
        )
    )

    draft = make_draft(
        benefits=(),
        technologies=(),
        suitability="",
        specifications_summary="",
    )

    formatted = formatter.format(
        context=make_context(),
        draft=draft,
    )

    assert (
        "<h2>Galvenās priekšrocības</h2>"
        in formatted.description_html
    )
    assert "<h2>Tehnoloģijas</h2>" in (
        formatted.description_html
    )
    assert "<h2>Piemērots</h2>" in (
        formatted.description_html
    )
    assert "<h2>Tehniskā informācija</h2>" in (
        formatted.description_html
    )


def test_conclusion_can_be_disabled():
    formatter = ProductFormatter(
        FormatterConfig(
            include_conclusion=False
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(),
    )

    assert (
        "Droša izvēle gardām maltītēm."
        not in formatted.description_html
    )


def test_empty_conclusion_creates_no_empty_paragraph():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            conclusion=""
        ),
    )

    assert "<p></p>" not in (
        formatted.description_html
    )


# ---------------------------------------------------------------------------
# HTML drošība un normalizācija
# ---------------------------------------------------------------------------


def test_html_escaping_is_applied():
    draft = make_draft(
        introduction=(
            '<script>alert("x")</script>'
        ),
        benefits=(
            "Drošs & ērts",
        ),
        technologies=(
            "A < B",
        ),
        suitability=(
            "<b>Piemērots</b>"
        ),
        specifications_summary=(
            '<img src="x">'
        ),
        conclusion="5 > 3",
    )

    formatted = ProductFormatter().format(
        context=make_context(),
        draft=draft,
    )

    assert "<script>" not in (
        formatted.description_html
    )
    assert "<b>Piemērots</b>" not in (
        formatted.description_html
    )
    assert "<img" not in (
        formatted.description_html
    )

    assert "&lt;script&gt;" in (
        formatted.description_html
    )
    assert "Drošs &amp; ērts" in (
        formatted.description_html
    )
    assert "A &lt; B" in (
        formatted.description_html
    )
    assert "5 &gt; 3" in (
        formatted.description_html
    )


def test_whitespace_is_normalized():
    draft = make_draft(
        title="  Weber   Spirit  ",
        introduction=(
            "  Ērts\n\n grils\u00a0ģimenei. "
        ),
        benefits=(
            "  Ātri   uzkarst. ",
        ),
        technologies=(
            "  GS4\n sistēma. ",
        ),
        suitability=(
            "  Terasei   un dārzam. "
        ),
        specifications_summary=(
            " Trīs\n degļi. "
        ),
        conclusion=(
            "  Laba   izvēle. "
        ),
    )

    formatted = ProductFormatter().format(
        context=make_context(),
        draft=draft,
    )

    assert formatted.title == "Weber Spirit"
    assert "Ērts grils ģimenei." in (
        formatted.description_html
    )
    assert "Ātri uzkarst." in (
        formatted.description_html
    )
    assert "GS4 sistēma." in (
        formatted.description_html
    )
    assert "Terasei un dārzam." in (
        formatted.description_html
    )
    assert "Trīs degļi." in (
        formatted.description_html
    )
    assert "Laba izvēle." in (
        formatted.description_html
    )


def test_unicode_is_preserved():
    draft = make_draft(
        title="Čuguna grils ģimenei",
        introduction=(
            "Ērti pagatavojiet gaļu, "
            "zivis un dārzeņus."
        ),
    )

    formatted = ProductFormatter().format(
        context=make_context(),
        draft=draft,
    )

    assert formatted.title == (
        "Čuguna grils ģimenei"
    )
    assert (
        "Ērti pagatavojiet gaļu, "
        "zivis un dārzeņus."
        in formatted.description_html
    )


# ---------------------------------------------------------------------------
# Īsais apraksts
# ---------------------------------------------------------------------------


def test_short_description_uses_intro_and_benefit():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert formatted.short_description == (
        "<p>Jaudīgs un daudzpusīgs grils "
        "ģimenes maltītēm. "
        "Ātri un vienmērīgi uzkarst.</p>"
    )


def test_short_description_avoids_duplicate():
    text = "Ātri uzkarst."

    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction=text,
            benefits=(text,),
        ),
    )

    assert formatted.short_description == (
        "<p>Ātri uzkarst.</p>"
    )


def test_short_description_falls_back_to_conclusion():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction="",
            benefits=(),
        ),
    )

    assert formatted.short_description == (
        "<p>Droša izvēle gardām maltītēm.</p>"
    )


def test_short_description_can_be_empty():
    formatter = ProductFormatter(
        FormatterConfig(
            include_conclusion=False
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(
            introduction="",
            benefits=(),
        ),
    )

    assert formatted.short_description == ""


def test_short_description_is_escaped():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction="Drošs & ērts.",
            benefits=("A < B",),
        ),
    )

    assert formatted.short_description == (
        "<p>Drošs &amp; ērts. "
        "A &lt; B</p>"
    )


def test_short_description_respects_limit():
    formatter = ProductFormatter(
        FormatterConfig(
            max_short_description_length=25
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(),
    )

    plain_text = (
        formatted.short_description
        .removeprefix("<p>")
        .removesuffix("</p>")
    )

    assert len(plain_text) <= 25
    assert plain_text.endswith("…")


# ---------------------------------------------------------------------------
# Meta description
# ---------------------------------------------------------------------------


def test_meta_description_is_plain_text():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "<p>" not in (
        formatted.meta_description
    )
    assert formatted.meta_description.startswith(
        "Jaudīgs un daudzpusīgs"
    )


def test_meta_description_combines_content():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert (
        "Jaudīgs un daudzpusīgs"
        in formatted.meta_description
    )
    assert (
        "Ātri un vienmērīgi uzkarst."
        in formatted.meta_description
    )


def test_meta_description_avoids_duplicate():
    text = "Ātri uzkarst."

    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction=text,
            benefits=(text,),
        ),
    )

    assert formatted.meta_description == text


def test_meta_description_respects_limit():
    formatter = ProductFormatter(
        FormatterConfig(
            max_meta_description_length=60
        )
    )

    formatted = formatter.format(
        context=make_context(),
        draft=make_draft(),
    )

    assert len(
        formatted.meta_description
    ) <= 60

    assert formatted.meta_description.endswith(
        "…"
    )


def test_meta_description_falls_back_to_conclusion():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction="",
            benefits=(),
        ),
    )

    assert formatted.meta_description == (
        "Droša izvēle gardām maltītēm."
    )


def test_meta_description_can_be_empty():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            introduction="",
            benefits=(),
            conclusion="",
        ),
    )

    assert formatted.meta_description == ""


@pytest.mark.parametrize(
    (
        "text",
        "limit",
        "expected",
    ),
    (
        (
            "Īss teksts",
            20,
            "Īss teksts",
        ),
        (
            "Viens ļoti garš teksts",
            12,
            "Viens ļoti…",
        ),
        (
            "Supergaršvārds",
            6,
            "Super…",
        ),
        (
            "abc",
            1,
            "…",
        ),
    ),
)
def test_truncate_at_word_boundary(
    text,
    limit,
    expected,
):
    assert _truncate_at_word_boundary(
        text,
        limit,
    ) == expected


# ---------------------------------------------------------------------------
# Search keywords
# ---------------------------------------------------------------------------


def test_keywords_include_brand():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "Weber" in (
        formatted.search_keywords
    )


def test_keywords_include_category():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "gāzes grils" in (
        formatted.search_keywords
    )


def test_keywords_include_title():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert (
        "Weber Spirit E-325 gāzes grils"
        in formatted.search_keywords
    )


def test_keywords_include_glossary_targets():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert (
        "Flavorizer aromatizējošās plāksnes"
        in formatted.search_keywords
    )

    assert "GS4" in (
        formatted.search_keywords
    )


def test_keywords_include_knowledge_keys():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "porcelain_enamel" in (
        formatted.search_keywords
    )


def test_keywords_include_title_tokens():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert "Spirit" in (
        formatted.search_keywords
    )

    assert "E-325" in (
        formatted.search_keywords
    )


def test_keywords_exclude_stopwords():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            title=(
                "Grils ar vāku un režģi"
            )
        ),
    )

    assert "ar" not in (
        formatted.search_keywords
    )
    assert "un" not in (
        formatted.search_keywords
    )
    assert "grils" not in (
        formatted.search_keywords
    )

    assert "vāku" in (
        formatted.search_keywords
    )
    assert "režģi" in (
        formatted.search_keywords
    )


def test_keywords_are_case_insensitively_unique():
    context = make_context(
        glossary_terms=(
            GlossaryMatch(
                source="Weber",
                target="WEBER",
            ),
        ),
        knowledge_keys=("weber",),
    )

    formatted = ProductFormatter().format(
        context=context,
        draft=make_draft(
            title="Weber WEBER Spirit"
        ),
    )

    assert sum(
        keyword.casefold() == "weber"
        for keyword
        in formatted.search_keywords
    ) == 1


def test_product_title_keyword_can_be_disabled():
    formatter = ProductFormatter(
        FormatterConfig(
            include_product_name_keyword=False
        )
    )

    draft = make_draft()

    formatted = formatter.format(
        context=make_context(),
        draft=draft,
    )

    assert draft.title not in (
        formatted.search_keywords
    )


@pytest.mark.parametrize(
    (
        "category",
        "expected",
    ),
    (
        (
            ProductCategory.GAS_GRILL,
            "gāzes grils",
        ),
        (
            ProductCategory.ELECTRIC_GRILL,
            "elektriskais grils",
        ),
        (
            ProductCategory.CHARCOAL_GRILL,
            "kokogļu grils",
        ),
        (
            ProductCategory.PELLET_GRILL,
            "granulu grils",
        ),
        (
            ProductCategory.GRIDDLE,
            "cepšanas virsma",
        ),
        (
            ProductCategory.SMOKER,
            "kūpinātava",
        ),
        (
            ProductCategory.ACCESSORY,
            "grila piederums",
        ),
        (
            ProductCategory.REPLACEMENT_PART,
            "rezerves daļa",
        ),
        (
            ProductCategory.OTHER,
            "grilēšanas prece",
        ),
    ),
)
def test_category_keyword_mapping(
    category,
    expected,
):
    formatted = ProductFormatter().format(
        context=make_context(
            category=category
        ),
        draft=make_draft(),
    )

    assert expected in (
        formatted.search_keywords
    )


# ---------------------------------------------------------------------------
# Metadata, warnings un determinisms
# ---------------------------------------------------------------------------


def test_warnings_are_preserved():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(
            warnings=(
                "Pirmais",
                "Otrais",
            )
        ),
    )

    assert formatted.warnings == (
        "Pirmais",
        "Otrais",
    )


def test_metadata_is_merged():
    context = make_context(
        metadata={
            "batch_id": "B-1",
            "shared": "context",
        }
    )

    draft = make_draft(
        metadata={
            "model": "fake",
            "shared": "draft",
        }
    )

    formatted = ProductFormatter().format(
        context=context,
        draft=draft,
    )

    assert formatted.metadata["batch_id"] == (
        "B-1"
    )
    assert formatted.metadata["model"] == (
        "fake"
    )
    assert formatted.metadata["shared"] == (
        "draft"
    )


def test_formatter_metadata_is_added():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert formatted.metadata["formatter"] == (
        "ProductFormatter"
    )

    assert (
        formatted.metadata["formatter_version"]
        == "1.0"
    )

    assert (
        formatted.metadata["product_category"]
        == "gas_grill"
    )


def test_metadata_is_immutable():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert isinstance(
        formatted.metadata,
        MappingProxyType,
    )

    with pytest.raises(TypeError):
        formatted.metadata["new"] = "value"


def test_formatter_is_deterministic():
    formatter = ProductFormatter()
    context = make_context()
    draft = make_draft()

    first = formatter.format(
        context=context,
        draft=draft,
    )

    second = formatter.format(
        context=context,
        draft=draft,
    )

    assert first == second


# ---------------------------------------------------------------------------
# Ievades validācija
# ---------------------------------------------------------------------------


def test_invalid_context_type_is_rejected():
    with pytest.raises(
        FormatterInputError
    ):
        ProductFormatter().format(
            context=object(),
            draft=make_draft(),
        )


def test_invalid_draft_type_is_rejected():
    with pytest.raises(
        FormatterInputError
    ):
        ProductFormatter().format(
            context=make_context(),
            draft=object(),
        )


def test_empty_title_is_rejected():
    with pytest.raises(
        FormatterInputError
    ):
        ProductFormatter().format(
            context=make_context(),
            draft=make_draft(
                title=" "
            ),
        )


def test_empty_sku_is_rejected():
    with pytest.raises(
        FormatterInputError
    ):
        ProductFormatter().format(
            context=make_context(
                sku=" "
            ),
            draft=make_draft(),
        )


def test_sku_whitespace_is_normalized():
    formatted = ProductFormatter().format(
        context=make_context(
            sku="  18412  "
        ),
        draft=make_draft(),
    )

    assert formatted.sku == "18412"


# ---------------------------------------------------------------------------
# Golden regression tests
# ---------------------------------------------------------------------------


def test_weber_spirit_golden_output():
    formatted = ProductFormatter().format(
        context=make_context(),
        draft=make_draft(),
    )

    assert formatted.sku == "18412"

    assert formatted.title == (
        "Weber Spirit E-325 gāzes grils"
    )

    assert formatted.short_description == (
        "<p>Jaudīgs un daudzpusīgs grils "
        "ģimenes maltītēm. "
        "Ātri un vienmērīgi uzkarst.</p>"
    )

    assert formatted.meta_description == (
        "Jaudīgs un daudzpusīgs grils "
        "ģimenes maltītēm. "
        "Ātri un vienmērīgi uzkarst. "
        "Viegli tīrāms pēc gatavošanas."
    )