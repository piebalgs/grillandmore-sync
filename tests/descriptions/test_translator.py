import json

import pytest

from src.descriptions.llm_client import (
    FakeLLMClient,
    LLMRequestError,
    LLMResponse,
)
from src.descriptions.models import (
    ProductCategory,
    ProductContext,
    PromptPackage,
    SectionId,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.translator import (
    InvalidJSONError,
    InvalidKnowledgeReferenceError,
    InvalidSchemaError,
    InvalidSectionError,
    TranslationClientError,
    TranslationPromptError,
    TranslationValidationError,
    Translator,
    TranslatorConfig,
)


class StubPromptBuilder:
    def __init__(self, result=None, error=None):
        self.result = result or PromptPackage("system", "user", {}, {"prompt_version": "1.0"})
        self.error = error
        self.calls = []

    def build(self, context):
        self.calls.append(context)
        if self.error:
            raise self.error
        return self.result


def make_context(*, sections=None, knowledge_keys=("Flavorizer Bars",)):
    return TranslationContext(
        product=ProductContext(
            sku="ABC-123",
            import_id="import-1",
            brand="Weber",
            product_name="Weber Genesis",
            category=ProductCategory.GAS_GRILL,
            knowledge_keys=knowledge_keys,
            sections=sections
            or (
                SectionId.INTRODUCTION,
                SectionId.BENEFITS,
                SectionId.TECHNOLOGIES,
                SectionId.SUITABILITY,
                SectionId.SPECIFICATIONS,
            ),
        )
    )


def valid_payload(**overrides):
    value = {
        "title": "Weber Genesis gāzes grils",
        "introduction": "Daudzpusīgs grils ikdienas gatavošanai.",
        "benefits": ["Vienmērīga karstuma sadale"],
        "technologies": ["Flavorizer stieņi palīdz sadalīt karstumu"],
        "suitability": "Piemērots ģimenes maltītēm.",
        "specifications_summary": "Gāzes grils ar izturīgu konstrukciju.",
        "conclusion": "Praktiska izvēle regulārai grilēšanai.",
        "used_knowledge_keys": ["Flavorizer Bars"],
        "warnings": [],
    }
    value.update(overrides)
    return value


def make_translator(payload=None, *, response=None, config=None, builder=None):
    if response is None:
        response = LLMResponse(content=json.dumps(payload or valid_payload()))
    return Translator(
        llm_client=FakeLLMClient([response]),
        prompt_builder=builder or StubPromptBuilder(),
        config=config,
    )


def test_translate_returns_translation_draft():
    assert isinstance(make_translator().translate(make_context()), TranslationDraft)


def test_prompt_builder_receives_context():
    builder = StubPromptBuilder()
    context = make_context()
    make_translator(builder=builder).translate(context)
    assert builder.calls == [context]


def test_llm_response_fields_are_mapped():
    draft = make_translator().translate(make_context())
    assert draft.title == "Weber Genesis gāzes grils"
    assert draft.benefits == ("Vienmērīga karstuma sadale",)


def test_empty_response_is_rejected():
    with pytest.raises(InvalidJSONError, match="tukša"):
        make_translator(response=LLMResponse(content=" ")).translate(make_context())


def test_invalid_json_is_rejected():
    with pytest.raises(InvalidJSONError, match="nav derīgs JSON"):
        make_translator(response=LLMResponse(content="{" )).translate(make_context())


def test_json_array_root_is_rejected():
    with pytest.raises(InvalidJSONError, match="JSON objektam"):
        make_translator(response=LLMResponse(content="[]")).translate(make_context())


def test_markdown_fence_is_rejected():
    content = "```json\n" + json.dumps(valid_payload()) + "\n```"
    with pytest.raises(InvalidJSONError, match="Markdown"):
        make_translator(response=LLMResponse(content=content)).translate(make_context())


def test_markdown_fence_check_can_be_disabled():
    content = json.dumps(valid_payload())
    draft = make_translator(
        response=LLMResponse(content=content),
        config=TranslatorConfig(reject_markdown_fences=False),
    ).translate(make_context())
    assert draft.title


@pytest.mark.parametrize("field", sorted(valid_payload()))
def test_missing_required_field_is_rejected(field):
    payload = valid_payload()
    del payload[field]
    with pytest.raises(InvalidSchemaError, match="Trūkst"):
        make_translator(payload).translate(make_context())


def test_unknown_field_is_rejected():
    with pytest.raises(InvalidSchemaError, match="neatļauti"):
        make_translator(valid_payload(extra="x")).translate(make_context())


@pytest.mark.parametrize(
    "field",
    ["title", "introduction", "suitability", "specifications_summary", "conclusion"],
)
def test_text_field_must_be_string(field):
    with pytest.raises(InvalidSchemaError, match=field):
        make_translator(valid_payload(**{field: 123})).translate(make_context())


@pytest.mark.parametrize(
    "field", ["benefits", "technologies", "used_knowledge_keys", "warnings"]
)
def test_list_field_must_be_list(field):
    with pytest.raises(InvalidSchemaError, match=field):
        make_translator(valid_payload(**{field: "not-list"})).translate(make_context())


def test_list_elements_must_be_strings():
    with pytest.raises(InvalidSchemaError, match="elementiem"):
        make_translator(valid_payload(benefits=[1])).translate(make_context())


def test_text_is_whitespace_normalized():
    draft = make_translator(valid_payload(title="  Weber\u00a0 Genesis\n grils  ")).translate(make_context())
    assert draft.title == "Weber Genesis grils"


def test_empty_list_items_are_removed():
    draft = make_translator(valid_payload(benefits=["", "  ", "Ieguvums"])).translate(make_context())
    assert draft.benefits == ("Ieguvums",)


def test_duplicate_list_items_are_removed_case_insensitively():
    draft = make_translator(valid_payload(benefits=["Ātri", " ātri "])).translate(make_context())
    assert draft.benefits == ("Ātri",)


def test_duplicate_removal_can_be_disabled():
    draft = make_translator(
        valid_payload(benefits=["Ātri", "ātri"]),
        config=TranslatorConfig(remove_duplicate_list_items=False),
    ).translate(make_context())
    assert draft.benefits == ("Ātri", "ātri")


def test_empty_title_is_rejected():
    with pytest.raises(TranslationValidationError, match="nosaukums"):
        make_translator(valid_payload(title=" ")).translate(make_context())


def test_title_requirement_can_be_disabled():
    draft = make_translator(
        valid_payload(title=" "),
        config=TranslatorConfig(require_title=False),
    ).translate(make_context())
    assert draft.title == ""


def test_empty_enabled_introduction_is_rejected():
    with pytest.raises(TranslationValidationError, match="Ievada"):
        make_translator(valid_payload(introduction="")).translate(make_context())


def test_empty_disabled_introduction_is_allowed():
    context = make_context(sections=(SectionId.BENEFITS,))
    payload = valid_payload(
        introduction="", technologies=[], suitability="", specifications_summary=""
    )
    assert make_translator(payload).translate(context).introduction == ""


def test_content_in_disabled_section_is_rejected():
    context = make_context(sections=(SectionId.INTRODUCTION,))
    with pytest.raises(InvalidSectionError, match="benefits"):
        make_translator(valid_payload()).translate(context)


def test_unknown_knowledge_key_is_rejected():
    with pytest.raises(InvalidKnowledgeReferenceError, match="Unknown"):
        make_translator(valid_payload(used_knowledge_keys=["Unknown"])).translate(make_context())


def test_empty_knowledge_references_are_allowed():
    draft = make_translator(valid_payload(used_knowledge_keys=[])).translate(make_context())
    assert draft.used_knowledge_keys == ()


def test_repeated_content_across_sections_is_rejected():
    with pytest.raises(TranslationValidationError, match="dublējas"):
        make_translator(valid_payload(conclusion="Piemērots ģimenes maltītēm.")).translate(make_context())


def test_repeated_section_check_can_be_disabled():
    draft = make_translator(
        valid_payload(conclusion="Piemērots ģimenes maltītēm."),
        config=TranslatorConfig(reject_duplicate_sections=False),
    ).translate(make_context())
    assert draft.conclusion


def test_llm_usage_and_identity_are_added_to_metadata():
    response = LLMResponse(
        content=json.dumps(valid_payload()),
        model="test-model",
        request_id="req-1",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    draft = make_translator(response=response).translate(make_context())
    assert draft.metadata["model"] == "test-model"
    assert draft.metadata["request_id"] == "req-1"
    assert draft.metadata["total_tokens"] == 15


def test_prompt_and_response_metadata_are_merged():
    builder = StubPromptBuilder(
        PromptPackage("s", "u", {}, {"prompt_version": "2.0", "sku": "ABC-123"})
    )
    response = LLMResponse(
        content=json.dumps(valid_payload()), metadata={"provider": "fake"}
    )
    draft = make_translator(response=response, builder=builder).translate(make_context())
    assert draft.metadata["prompt_version"] == "2.0"
    assert draft.metadata["provider"] == "fake"


def test_llm_client_error_is_wrapped():
    translator = Translator(
        llm_client=FakeLLMClient([LLMRequestError("offline")]),
        prompt_builder=StubPromptBuilder(),
    )
    with pytest.raises(TranslationClientError, match="offline"):
        translator.translate(make_context())


def test_unexpected_client_error_is_wrapped():
    translator = Translator(
        llm_client=FakeLLMClient([ValueError("boom")]),
        prompt_builder=StubPromptBuilder(),
    )
    with pytest.raises(TranslationClientError, match="neizdevās"):
        translator.translate(make_context())


def test_invalid_client_return_type_is_rejected():
    class BadClient:
        def generate(self, prompt):
            return "bad"

    with pytest.raises(TranslationClientError, match="LLMResponse"):
        Translator(llm_client=BadClient(), prompt_builder=StubPromptBuilder()).translate(make_context())


def test_prompt_builder_error_is_wrapped():
    with pytest.raises(TranslationPromptError, match="Prompta"):
        make_translator(builder=StubPromptBuilder(error=ValueError("boom"))).translate(make_context())


def test_invalid_prompt_builder_return_type_is_rejected():
    with pytest.raises(TranslationPromptError, match="PromptPackage"):
        make_translator(builder=StubPromptBuilder(result="bad")).translate(make_context())
