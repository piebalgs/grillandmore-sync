import json
from datetime import date

import pytest

from src.descriptions.knowledge_base import KnowledgeBase
from src.descriptions.models import (
    GlossaryMatch,
    KnowledgeCategory,
    KnowledgeItem,
    ProductCategory,
    ProductContext,
    PromptPackage,
    SectionId,
    TranslationContext,
)
from src.descriptions.prompt_builder import (
    PromptBuilder,
    PromptBuilderConfig,
    PromptBuilderError,
)


def make_context(**overrides):
    product = ProductContext(
        sku="ABC-123",
        import_id="import-1",
        brand="Weber",
        product_name="Weber Genesis gas grill",
        category=ProductCategory.GAS_GRILL,
        glossary_terms=(
            GlossaryMatch(
                source="gas grill",
                target="gāzes grils",
                note="Approved term",
            ),
        ),
        knowledge_keys=(),
        sections=(
            SectionId.INTRODUCTION,
            SectionId.BENEFITS,
            SectionId.SUITABILITY,
            SectionId.SPECIFICATIONS,
        ),
        warnings=("Editorial warning",),
        metadata={},
    )
    values = {
        "product": product,
        "source_language": "en",
        "target_language": "lv",
        "source_description": "A compact gas grill.",
        "source_sales_arguments": ("Compact design",),
        "source_benefits": ("Easy everyday grilling",),
        "source_features": ("Porcelain-enamelled grate",),
        "source_specifications": {"barbecue_type": "GAS"},
        "translated_specifications": {
            "barbecue_type": ("Grila veids", "Gāzes grils")
        },
        "style_instructions": "Raksti skaidri un tehniski precīzi.",
        "metadata": {},
    }
    values.update(overrides)
    return TranslationContext(**values)


def replace_product(context, **changes):
    values = {
        "sku": context.product.sku,
        "import_id": context.product.import_id,
        "brand": context.product.brand,
        "product_name": context.product.product_name,
        "category": context.product.category,
        "glossary_terms": context.product.glossary_terms,
        "knowledge_keys": context.product.knowledge_keys,
        "sections": context.product.sections,
        "warnings": context.product.warnings,
        "metadata": context.product.metadata,
    }
    values.update(changes)
    return make_context(product=ProductContext(**values))


def test_build_returns_prompt_package():
    result = PromptBuilder(knowledge_base=KnowledgeBase()).build(make_context())
    assert isinstance(result, PromptPackage)


def test_user_prompt_is_valid_json():
    result = PromptBuilder(knowledge_base=KnowledgeBase()).build(make_context())
    assert json.loads(result.user_prompt)["product"]["sku"] == "ABC-123"


def test_build_is_deterministic():
    builder = PromptBuilder(knowledge_base=KnowledgeBase())
    context = make_context()
    assert builder.build(context) == builder.build(context)


def test_system_prompt_forbids_invented_facts():
    result = PromptBuilder(knowledge_base=KnowledgeBase()).build(make_context())
    assert "Neizdomā funkcijas" in result.system_prompt


def test_system_prompt_forbids_html():
    result = PromptBuilder(knowledge_base=KnowledgeBase()).build(make_context())
    assert "Neraksti HTML" in result.system_prompt


def test_system_prompt_requires_json_only():
    result = PromptBuilder(knowledge_base=KnowledgeBase()).build(make_context())
    assert "tikai derīgu JSON objektu" in result.system_prompt


def test_json_only_rule_can_be_relaxed():
    builder = PromptBuilder(
        knowledge_base=KnowledgeBase(),
        config=PromptBuilderConfig(require_json_only=False),
    )
    assert "tikai derīgu JSON objektu" not in builder.build(
        make_context()
    ).system_prompt


def test_selected_sections_are_enabled():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    sections = {item["section_id"]: item for item in payload["sections"]}
    assert sections["introduction"]["enabled"] is True
    assert sections["technologies"]["enabled"] is False


def test_inactive_section_instruction_is_explicit():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    assert "Neaktīvo sadaļu laukiem" in payload["task"]


def test_glossary_target_is_included():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    assert payload["terminology"][0]["required_target"] == "gāzes grils"


def test_translated_specification_is_structured():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    assert payload["source"]["translated_specifications"]["barbecue_type"] == {
        "label": "Grila veids",
        "value": "Gāzes grils",
    }


def test_source_specifications_are_included_by_default():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    assert payload["source"]["source_specifications"]["barbecue_type"] == "GAS"


def test_source_specifications_can_be_hidden():
    builder = PromptBuilder(
        knowledge_base=KnowledgeBase(),
        config=PromptBuilderConfig(include_source_specifications=False),
    )
    assert "source_specifications" not in builder.build_user_payload(
        make_context()
    )["source"]


def test_context_warnings_are_included_by_default():
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(make_context())
    assert payload["context_warnings"] == ["Editorial warning"]


def test_context_warnings_can_be_hidden():
    builder = PromptBuilder(
        knowledge_base=KnowledgeBase(),
        config=PromptBuilderConfig(include_context_warnings=False),
    )
    assert "context_warnings" not in builder.build_user_payload(make_context())


def test_only_selected_verified_knowledge_is_included():
    item = KnowledgeItem(
        key="Flavorizer Bars",
        category=KnowledgeCategory.COOKING_SYSTEM,
        translation="Flavorizer stieņi",
        short_description="Heat distribution system.",
        explanation="Covers burner area.",
        customer_benefit="Supports even cooking.",
        source="Official manufacturer source",
        evidence=("Manufacturer product page",),
        verified=True,
        last_reviewed=date(2026, 7, 1),
    )
    knowledge_base = KnowledgeBase((item,))
    context = replace_product(
        make_context(),
        knowledge_keys=("Flavorizer Bars",),
        sections=make_context().product.sections + (SectionId.TECHNOLOGIES,),
    )
    payload = PromptBuilder(
        knowledge_base=knowledge_base
    ).build_user_payload(context)
    assert payload["knowledge"][0]["key"] == "Flavorizer Bars"


def test_unavailable_knowledge_key_is_not_invented():
    context = replace_product(
        make_context(),
        knowledge_keys=("Unknown concept",),
    )
    payload = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build_user_payload(context)
    assert payload["knowledge"] == []


def test_response_schema_rejects_additional_properties():
    assert PromptBuilder.response_schema()["additionalProperties"] is False


def test_response_schema_has_all_translation_fields():
    assert set(PromptBuilder.response_schema()["required"]) == {
        "title",
        "introduction",
        "benefits",
        "technologies",
        "suitability",
        "specifications_summary",
        "conclusion",
        "used_knowledge_keys",
        "warnings",
    }


def test_metadata_is_stable_and_useful():
    package = PromptBuilder(
        knowledge_base=KnowledgeBase()
    ).build(make_context())
    assert package.metadata["prompt_version"] == "1.0"
    assert package.metadata["section_count"] == 4
    assert package.metadata["glossary_term_count"] == 1


def test_missing_sku_is_rejected():
    with pytest.raises(PromptBuilderError, match="SKU"):
        PromptBuilder(knowledge_base=KnowledgeBase()).build(
            replace_product(make_context(), sku="")
        )


def test_missing_product_name_is_rejected():
    with pytest.raises(PromptBuilderError, match="nosaukuma"):
        PromptBuilder(knowledge_base=KnowledgeBase()).build(
            replace_product(make_context(), product_name="")
        )


def test_no_sections_is_rejected():
    with pytest.raises(PromptBuilderError, match="neviena sadaļa"):
        PromptBuilder(knowledge_base=KnowledgeBase()).build(
            replace_product(make_context(), sections=())
        )
