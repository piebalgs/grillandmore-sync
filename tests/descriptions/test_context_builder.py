"""Tests for src.descriptions.context_builder."""

from src.descriptions.context_builder import (
    ContextBuilder,
    ContextBuilderConfig,
)
from src.descriptions.models import ProductCategory, SectionId
from src.descriptions.parser import (
    ConsumerBenefit,
    ProductDescription,
    ProductFeature,
)


def make_product(**overrides: object) -> ProductDescription:
    values: dict[str, object] = {
        "sku": "1500539",
        "import_id": "demo-1",
        "title": "Weber Genesis gas grill",
        "source_description": (
            "Flavorizer Bars and Infinity Ignition support everyday grilling."
        ),
        "sales_arguments": ("Large cooking area",),
        "consumer_benefits": (
            ConsumerBenefit(
                title="Even heat",
                description="Helps cook food consistently.",
            ),
        ),
        "product_features": (
            ProductFeature(
                title="Flavorizer Bars",
                description="Cover the burner area.",
            ),
        ),
        "specifications": {
            "barbecue_type": "GAS",
            "guarantee": "10_L",
            "color": "Black",
        },
        "raw": {"Brand": "Weber"},
    }
    values.update(overrides)
    return ProductDescription(**values)


def test_build_returns_translation_context() -> None:
    context = ContextBuilder().build(make_product())
    assert context.sku == "1500539"
    assert context.product_name == "Weber Genesis gas grill"


def test_brand_is_read_from_structured_raw_data() -> None:
    context = ContextBuilder().build(make_product(raw={"Brand": "Napoleon"}))
    assert context.brand == "Napoleon"


def test_brand_is_detected_from_source_text() -> None:
    product = make_product(raw={}, title="Weber Traveler")
    assert ContextBuilder().detect_brand(product) == "Weber"


def test_default_brand_is_used_when_source_has_no_brand() -> None:
    product = make_product(
        raw={},
        title="Portable barbecue",
        source_description="Compact cooking appliance.",
    )
    builder = ContextBuilder(
        config=ContextBuilderConfig(default_brand="Unknown")
    )
    assert builder.detect_brand(product) == "Unknown"


def test_structured_category_has_priority() -> None:
    product = make_product(
        title="Charcoal-style gas grill",
        specifications={"barbecue_type": "GAS"},
    )
    assert ContextBuilder().detect_category(product) == ProductCategory.GAS_GRILL


def test_category_can_be_detected_from_text() -> None:
    product = make_product(
        title="Portable charcoal grill",
        source_description="",
        specifications={},
    )
    assert (
        ContextBuilder().detect_category(product)
        == ProductCategory.CHARCOAL_GRILL
    )


def test_unknown_category_is_explicit() -> None:
    product = make_product(
        title="Outdoor product",
        source_description="Useful item.",
        sales_arguments=(),
        consumer_benefits=(),
        product_features=(),
        specifications={},
    )
    assert ContextBuilder().detect_category(product) == ProductCategory.OTHER


def test_glossary_term_is_collected_once() -> None:
    product = make_product(
        source_description="Flavorizer Bars. Flavorizer Bars.",
        product_features=(),
    )
    matches = ContextBuilder().collect_glossary_terms(product)
    keys = [item.source.casefold() for item in matches]
    assert keys.count("flavorizer bars") == 1


def test_glossary_match_contains_approved_target() -> None:
    matches = ContextBuilder().collect_glossary_terms(make_product())
    flavorizer = next(
        item for item in matches if item.source == "Flavorizer Bars"
    )
    assert flavorizer.target == "Flavorizer aromatizējošās plāksnes"


def test_verified_knowledge_is_collected() -> None:
    context = ContextBuilder().build(make_product())
    assert "Flavorizer Bars" in context.knowledge_keys


def test_draft_knowledge_is_hidden_by_default() -> None:
    context = ContextBuilder().build(make_product())
    assert "Infinity Ignition" not in context.knowledge_keys


def test_draft_knowledge_can_be_included_explicitly() -> None:
    builder = ContextBuilder(
        config=ContextBuilderConfig(include_unverified_knowledge=True)
    )
    context = builder.build(make_product())
    assert "Infinity Ignition" in context.knowledge_keys


def test_sections_follow_available_data() -> None:
    context = ContextBuilder().build(make_product())
    assert context.product.sections == (
        SectionId.INTRODUCTION,
        SectionId.BENEFITS,
        SectionId.TECHNOLOGIES,
        SectionId.SUITABILITY,
        SectionId.SPECIFICATIONS,
    )


def test_minimal_product_gets_only_introduction() -> None:
    product = make_product(
        title="Unknown item",
        source_description="",
        sales_arguments=(),
        consumer_benefits=(),
        product_features=(),
        specifications={},
    )
    context = ContextBuilder().build(product)
    assert context.product.sections == (SectionId.INTRODUCTION,)


def test_missing_source_description_creates_warning() -> None:
    context = ContextBuilder().build(
        make_product(source_description="")
    )
    assert "Nav avota produkta apraksta." in context.product.warnings


def test_missing_specifications_create_warning() -> None:
    context = ContextBuilder().build(
        make_product(specifications={})
    )
    assert (
        "Nav strukturētu tehnisko specifikāciju."
        in context.product.warnings
    )


def test_unknown_category_creates_warning() -> None:
    product = make_product(
        title="Outdoor item",
        source_description="General product.",
        sales_arguments=(),
        consumer_benefits=(),
        product_features=(),
        specifications={},
    )
    context = ContextBuilder().build(product)
    assert (
        "Produkta kategoriju neizdevās noteikt deterministiski."
        in context.product.warnings
    )


def test_specifications_are_translated_deterministically() -> None:
    context = ContextBuilder().build(make_product())
    assert context.translated_specifications["barbecue_type"] == (
        "Grila veids",
        "Gāzes grils",
    )
    assert context.translated_specifications["guarantee"] == (
        "Garantija",
        "10 gadu ierobežotā garantija",
    )


def test_benefits_and_features_are_flattened_predictably() -> None:
    context = ContextBuilder().build(make_product())
    assert context.source_benefits == (
        "Even heat — Helps cook food consistently.",
    )
    assert context.source_features == (
        "Flavorizer Bars — Cover the burner area.",
    )


def test_build_is_deterministic() -> None:
    builder = ContextBuilder()
    product = make_product()
    assert builder.build(product) == builder.build(product)


def test_source_product_is_not_mutated() -> None:
    builder = ContextBuilder()
    product = make_product()
    original_specs = dict(product.specifications)
    builder.build(product)
    assert product.specifications == original_specs


def test_metadata_is_stable_and_useful() -> None:
    context = ContextBuilder().build(
        make_product(
            title_line_1="Genesis",
            title_line_2="EP-435",
            title_line_3="Black",
        )
    )
    assert context.product.metadata["source_title_lines"] == (
        "Genesis",
        "EP-435",
        "Black",
    )
    assert context.metadata["parser_import_id"] == "demo-1"
