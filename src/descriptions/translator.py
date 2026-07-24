"""Validated orchestration from TranslationContext to TranslationDraft."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Protocol

from src.descriptions.llm_client import LLMClient, LLMClientError, LLMResponse
from src.descriptions.models import (
    PromptPackage,
    SectionId,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.prompt_builder import PromptBuilder, PromptBuilderError


class TranslationError(RuntimeError):
    """Base error raised by the translation orchestration layer."""


class TranslationPromptError(TranslationError):
    """Raised when a prompt cannot be built."""


class TranslationClientError(TranslationError):
    """Raised when the configured LLM client fails."""


class InvalidJSONError(TranslationError):
    """Raised when the LLM response is not one plain JSON object."""


class InvalidSchemaError(TranslationError):
    """Raised when the decoded JSON does not match the required contract."""


class InvalidKnowledgeReferenceError(TranslationError):
    """Raised when the response cites knowledge absent from the context."""


class InvalidSectionError(TranslationError):
    """Raised when disabled sections contain generated content."""


class TranslationValidationError(TranslationError):
    """Raised when normalized content violates business rules."""


class PromptBuilderLike(Protocol):
    """Small dependency-injection contract required by Translator."""

    def build(self, context: TranslationContext) -> PromptPackage:
        ...


@dataclass(frozen=True, slots=True)
class TranslatorConfig:
    """Deterministic normalization and validation settings."""

    remove_duplicate_list_items: bool = True
    reject_duplicate_sections: bool = True
    reject_markdown_fences: bool = True
    require_title: bool = True
    require_introduction_when_enabled: bool = True


_TEXT_FIELDS = (
    "title",
    "introduction",
    "suitability",
    "specifications_summary",
    "conclusion",
)
_LIST_FIELDS = (
    "benefits",
    "technologies",
    "used_knowledge_keys",
    "warnings",
)
_REQUIRED_FIELDS = frozenset((*_TEXT_FIELDS, *_LIST_FIELDS))
_FIELD_BY_SECTION = {
    SectionId.INTRODUCTION: "introduction",
    SectionId.BENEFITS: "benefits",
    SectionId.TECHNOLOGIES: "technologies",
    SectionId.SUITABILITY: "suitability",
    SectionId.SPECIFICATIONS: "specifications_summary",
}
_SPACE_RE = re.compile(r"\s+")
_FENCE_RE = re.compile(r"^\s*```|```\s*$", re.MULTILINE)


class Translator:
    """Build a prompt, call an LLM, validate output and return a draft."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        prompt_builder: PromptBuilderLike | None = None,
        config: TranslatorConfig | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.config = config or TranslatorConfig()

    def translate(self, context: TranslationContext) -> TranslationDraft:
        """Execute one translation attempt without retries."""
        prompt = self._build_prompt(context)
        response = self._call_llm(prompt)
        payload = self._parse_json(response.content)
        self._validate_schema(payload)
        normalized = self._normalize_payload(payload)
        self._validate_sections(normalized, context)
        self._validate_business_rules(normalized, context)
        return self._build_draft(normalized, prompt, response)

    def _build_prompt(self, context: TranslationContext) -> PromptPackage:
        try:
            prompt = self.prompt_builder.build(context)
        except PromptBuilderError as exc:
            raise TranslationPromptError(str(exc)) from exc
        except Exception as exc:
            raise TranslationPromptError("Prompta izveide neizdevās.") from exc
        if not isinstance(prompt, PromptPackage):
            raise TranslationPromptError("PromptBuilder neatgrieza PromptPackage.")
        return prompt

    def _call_llm(self, prompt: PromptPackage) -> LLMResponse:
        try:
            response = self.llm_client.generate(prompt)
        except LLMClientError as exc:
            raise TranslationClientError(str(exc)) from exc
        except Exception as exc:
            raise TranslationClientError("LLM izsaukums neizdevās.") from exc
        if not isinstance(response, LLMResponse):
            raise TranslationClientError("LLMClient neatgrieza LLMResponse.")
        return response

    def _parse_json(self, content: str) -> dict[str, Any]:
        if not content.strip():
            raise InvalidJSONError("LLM atbilde ir tukša.")
        if self.config.reject_markdown_fences and _FENCE_RE.search(content):
            raise InvalidJSONError("LLM atbilde satur Markdown koda žogu.")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidJSONError(
                f"LLM atbilde nav derīgs JSON: {exc.msg}."
            ) from exc
        if not isinstance(value, dict):
            raise InvalidJSONError("LLM atbildes saknei jābūt JSON objektam.")
        return value

    @staticmethod
    def _validate_schema(payload: Mapping[str, Any]) -> None:
        keys = set(payload)
        missing = _REQUIRED_FIELDS - keys
        unknown = keys - _REQUIRED_FIELDS
        if missing:
            raise InvalidSchemaError(
                "Trūkst obligāto lauku: " + ", ".join(sorted(missing)) + "."
            )
        if unknown:
            raise InvalidSchemaError(
                "Atrasti neatļauti lauki: " + ", ".join(sorted(unknown)) + "."
            )
        for field_name in _TEXT_FIELDS:
            if not isinstance(payload[field_name], str):
                raise InvalidSchemaError(f"Laukam {field_name} jābūt tekstam.")
        for field_name in _LIST_FIELDS:
            value = payload[field_name]
            if not isinstance(value, list):
                raise InvalidSchemaError(f"Laukam {field_name} jābūt sarakstam.")
            if any(not isinstance(item, str) for item in value):
                raise InvalidSchemaError(
                    f"Lauka {field_name} elementiem jābūt tekstam."
                )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return _SPACE_RE.sub(" ", value.replace("\u00a0", " ").strip())

    def _normalize_list(self, values: list[str]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = self._normalize_text(value)
            if not cleaned:
                continue
            marker = cleaned.casefold()
            if self.config.remove_duplicate_list_items and marker in seen:
                continue
            seen.add(marker)
            result.append(cleaned)
        return tuple(result)

    def _normalize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = {
            field_name: self._normalize_text(payload[field_name])
            for field_name in _TEXT_FIELDS
        }
        normalized.update(
            {
                field_name: self._normalize_list(payload[field_name])
                for field_name in _LIST_FIELDS
            }
        )
        return normalized

    @staticmethod
    def _has_content(value: str | tuple[str, ...]) -> bool:
        return bool(value)

    def _validate_sections(
        self,
        payload: Mapping[str, Any],
        context: TranslationContext,
    ) -> None:
        enabled = set(context.product.sections)
        for section_id, field_name in _FIELD_BY_SECTION.items():
            if section_id not in enabled and self._has_content(payload[field_name]):
                raise InvalidSectionError(
                    f"Neaktīvajai sadaļai {section_id.value} jābūt tukšai."
                )

    def _validate_business_rules(
        self,
        payload: Mapping[str, Any],
        context: TranslationContext,
    ) -> None:
        if self.config.require_title and not payload["title"]:
            raise TranslationValidationError("Produkta nosaukums ir tukšs.")
        if (
            self.config.require_introduction_when_enabled
            and SectionId.INTRODUCTION in context.product.sections
            and not payload["introduction"]
        ):
            raise TranslationValidationError("Ievada sadaļa ir tukša.")

        allowed = set(context.knowledge_keys)
        invalid = [key for key in payload["used_knowledge_keys"] if key not in allowed]
        if invalid:
            raise InvalidKnowledgeReferenceError(
                "Neatļautas zināšanu atslēgas: " + ", ".join(invalid) + "."
            )

        if self.config.reject_duplicate_sections:
            self._reject_repeated_section_content(payload)

    @staticmethod
    def _reject_repeated_section_content(payload: Mapping[str, Any]) -> None:
        comparable: list[tuple[str, str]] = []
        for field_name in _TEXT_FIELDS[1:]:
            value = payload[field_name]
            if value:
                comparable.append((field_name, value.casefold()))
        for field_name in ("benefits", "technologies"):
            for item in payload[field_name]:
                comparable.append((field_name, item.casefold()))

        seen: dict[str, str] = {}
        for field_name, value in comparable:
            previous = seen.get(value)
            if previous is not None and previous != field_name:
                raise TranslationValidationError(
                    f"Saturs dublējas laukos {previous} un {field_name}."
                )
            seen[value] = field_name

    @staticmethod
    def _build_draft(
        payload: Mapping[str, Any],
        prompt: PromptPackage,
        response: LLMResponse,
    ) -> TranslationDraft:
        metadata = {
            **dict(prompt.metadata),
            **dict(response.metadata),
            "model": response.model,
            "request_id": response.request_id,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        }
        return TranslationDraft(
            title=payload["title"],
            introduction=payload["introduction"],
            benefits=payload["benefits"],
            technologies=payload["technologies"],
            suitability=payload["suitability"],
            specifications_summary=payload["specifications_summary"],
            conclusion=payload["conclusion"],
            used_knowledge_keys=payload["used_knowledge_keys"],
            warnings=payload["warnings"],
            metadata=metadata,
        )
