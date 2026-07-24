"""Deterministic formatting of translated product content for WooCommerce."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from src.descriptions.models import (
    FormattedProduct,
    ProductCategory,
    SectionId,
    TranslationContext,
    TranslationDraft,
)


class FormatterError(RuntimeError):
    """Base error raised by the product formatting layer."""


class FormatterConfigurationError(FormatterError):
    """Raised when formatter configuration is invalid."""


class FormatterInputError(FormatterError):
    """Raised when formatter receives invalid input."""


@dataclass(frozen=True, slots=True)
class FormatterConfig:
    """Deterministic WooCommerce formatting settings."""

    heading_level: int = 2
    max_short_description_length: int = 320
    max_meta_description_length: int = 155

    include_conclusion: bool = True
    include_empty_sections: bool = False
    include_product_name_keyword: bool = True

    benefits_heading: str = "Galvenās priekšrocības"
    technologies_heading: str = "Tehnoloģijas"
    suitability_heading: str = "Piemērots"
    specifications_heading: str = "Tehniskā informācija"

    def __post_init__(self) -> None:
        if not 1 <= self.heading_level <= 6:
            raise FormatterConfigurationError(
                "heading_level jābūt veselam skaitlim no 1 līdz 6."
            )

        if self.max_short_description_length < 1:
            raise FormatterConfigurationError(
                "max_short_description_length jābūt lielākam par nulli."
            )

        if self.max_meta_description_length < 1:
            raise FormatterConfigurationError(
                "max_meta_description_length jābūt lielākam par nulli."
            )

        headings = (
            self.benefits_heading,
            self.technologies_heading,
            self.suitability_heading,
            self.specifications_heading,
        )

        if any(
            not isinstance(heading, str) or not heading.strip()
            for heading in headings
        ):
            raise FormatterConfigurationError(
                "Visiem sadaļu virsrakstiem jābūt netukšam tekstam."
            )


class HTMLBuilder:
    """Small deterministic HTML builder that escapes all supplied text."""

    def __init__(self, *, heading_level: int = 2) -> None:
        if not 1 <= heading_level <= 6:
            raise FormatterConfigurationError(
                "heading_level jābūt veselam skaitlim no 1 līdz 6."
            )

        self.heading_level = heading_level
        self._blocks: list[str] = []

    def paragraph(self, text: str) -> None:
        cleaned = _normalize_text(text)

        if cleaned:
            self._blocks.append(f"<p>{escape(cleaned)}</p>")

    def heading(self, text: str) -> None:
        cleaned = _normalize_text(text)

        if not cleaned:
            return

        tag = f"h{self.heading_level}"
        self._blocks.append(f"<{tag}>{escape(cleaned)}</{tag}>")

    def unordered_list(self, items: Iterable[str]) -> None:
        cleaned_items = tuple(
            cleaned
            for item in items
            if (cleaned := _normalize_text(item))
        )

        if not cleaned_items:
            return

        lines = ["<ul>"]
        lines.extend(
            f"  <li>{escape(item)}</li>"
            for item in cleaned_items
        )
        lines.append("</ul>")

        self._blocks.append("\n".join(lines))

    @property
    def html(self) -> str:
        """Return HTML blocks separated by one empty line."""

        return "\n\n".join(self._blocks)


_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)

_CATEGORY_KEYWORDS: Mapping[ProductCategory, str] = MappingProxyType(
    {
        ProductCategory.GAS_GRILL: "gāzes grils",
        ProductCategory.ELECTRIC_GRILL: "elektriskais grils",
        ProductCategory.CHARCOAL_GRILL: "kokogļu grils",
        ProductCategory.PELLET_GRILL: "granulu grils",
        ProductCategory.GRIDDLE: "cepšanas virsma",
        ProductCategory.SMOKER: "kūpinātava",
        ProductCategory.ACCESSORY: "grila piederums",
        ProductCategory.REPLACEMENT_PART: "rezerves daļa",
        ProductCategory.OTHER: "grilēšanas prece",
    }
)

_KEYWORD_STOPWORDS = frozenset(
    {
        "ar",
        "bez",
        "grils",
        "grila",
        "ir",
        "komplekts",
        "melns",
        "melna",
        "modelis",
        "no",
        "par",
        "pie",
        "prece",
        "produkts",
        "un",
        "vai",
    }
)


def _normalize_text(value: str) -> str:
    """Normalize whitespace while preserving Unicode text."""

    if not isinstance(value, str):
        raise FormatterInputError(
            "Formatējamajai vērtībai jābūt tekstam."
        )

    return _SPACE_RE.sub(
        " ",
        value.replace("\u00a0", " ").strip(),
    )


def _truncate_at_word_boundary(
    text: str,
    max_length: int,
) -> str:
    """Truncate text without cutting a word whenever possible."""

    cleaned = _normalize_text(text)

    if len(cleaned) <= max_length:
        return cleaned

    if max_length == 1:
        return "…"

    available = max_length - 1
    candidate = cleaned[: available + 1]
    boundary = candidate.rfind(" ", 0, available + 1)

    if boundary <= 0:
        return cleaned[:available].rstrip() + "…"

    return cleaned[:boundary].rstrip(" ,;:-") + "…"


class ProductFormatter:
    """Convert TranslationDraft into WooCommerce-ready content."""

    def __init__(
        self,
        config: FormatterConfig | None = None,
    ) -> None:
        self.config = config or FormatterConfig()

    def format(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
    ) -> FormattedProduct:
        """Format one validated translation draft."""

        self._validate_inputs(
            context=context,
            draft=draft,
        )

        title = _normalize_text(draft.title)

        short_description = self._build_short_description(
            draft
        )

        description_html = self._build_html(
            context=context,
            draft=draft,
        )

        meta_description = self._build_meta_description(
            draft
        )

        search_keywords = self._build_search_keywords(
            context=context,
            draft=draft,
        )

        metadata: dict[str, Any] = {
            **dict(context.metadata),
            **dict(draft.metadata),
            "formatter": "ProductFormatter",
            "formatter_version": "1.0",
            "product_category": context.product_category.value,
        }

        return FormattedProduct(
            sku=_normalize_text(context.sku),
            title=title,
            short_description=short_description,
            description_html=description_html,
            meta_description=meta_description,
            search_keywords=search_keywords,
            warnings=tuple(draft.warnings),
            metadata=MappingProxyType(metadata),
        )

    @staticmethod
    def _validate_inputs(
        *,
        context: TranslationContext,
        draft: TranslationDraft,
    ) -> None:
        if not isinstance(context, TranslationContext):
            raise FormatterInputError(
                "context jābūt TranslationContext instancei."
            )

        if not isinstance(draft, TranslationDraft):
            raise FormatterInputError(
                "draft jābūt TranslationDraft instancei."
            )

        if not _normalize_text(context.sku):
            raise FormatterInputError(
                "Produkta SKU nedrīkst būt tukšs."
            )

        if not _normalize_text(draft.title):
            raise FormatterInputError(
                "Produkta nosaukums nedrīkst būt tukšs."
            )

    def _build_short_description(
        self,
        draft: TranslationDraft,
    ) -> str:
        candidates: list[str] = []

        introduction = _normalize_text(draft.introduction)

        if introduction:
            candidates.append(introduction)

        if draft.benefits:
            first_benefit = _normalize_text(
                draft.benefits[0]
            )

            existing = {
                item.casefold()
                for item in candidates
            }

            if (
                first_benefit
                and first_benefit.casefold() not in existing
            ):
                candidates.append(first_benefit)

        if (
            not candidates
            and self.config.include_conclusion
        ):
            conclusion = _normalize_text(
                draft.conclusion
            )

            if conclusion:
                candidates.append(conclusion)

        text = " ".join(candidates)

        text = _truncate_at_word_boundary(
            text,
            self.config.max_short_description_length,
        )

        if not text:
            return ""

        return f"<p>{escape(text)}</p>"

    def _build_html(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
    ) -> str:
        builder = HTMLBuilder(
            heading_level=self.config.heading_level
        )

        enabled_sections = set(
            context.product.sections
        )

        if (
            SectionId.INTRODUCTION in enabled_sections
            or self.config.include_empty_sections
        ):
            builder.paragraph(
                draft.introduction
            )

        self._add_list_section(
            builder=builder,
            enabled=SectionId.BENEFITS in enabled_sections,
            heading=self.config.benefits_heading,
            items=draft.benefits,
        )

        self._add_list_section(
            builder=builder,
            enabled=SectionId.TECHNOLOGIES in enabled_sections,
            heading=self.config.technologies_heading,
            items=draft.technologies,
        )

        self._add_text_section(
            builder=builder,
            enabled=SectionId.SUITABILITY in enabled_sections,
            heading=self.config.suitability_heading,
            text=draft.suitability,
        )

        self._add_text_section(
            builder=builder,
            enabled=SectionId.SPECIFICATIONS in enabled_sections,
            heading=self.config.specifications_heading,
            text=draft.specifications_summary,
        )

        if self.config.include_conclusion:
            builder.paragraph(
                draft.conclusion
            )

        return builder.html

    def _add_list_section(
        self,
        *,
        builder: HTMLBuilder,
        enabled: bool,
        heading: str,
        items: tuple[str, ...],
    ) -> None:
        if not enabled:
            return

        cleaned_items = tuple(
            cleaned
            for item in items
            if (cleaned := _normalize_text(item))
        )

        if (
            not cleaned_items
            and not self.config.include_empty_sections
        ):
            return

        builder.heading(heading)
        builder.unordered_list(cleaned_items)

    def _add_text_section(
        self,
        *,
        builder: HTMLBuilder,
        enabled: bool,
        heading: str,
        text: str,
    ) -> None:
        if not enabled:
            return

        cleaned = _normalize_text(text)

        if (
            not cleaned
            and not self.config.include_empty_sections
        ):
            return

        builder.heading(heading)
        builder.paragraph(cleaned)

    def _build_meta_description(
        self,
        draft: TranslationDraft,
    ) -> str:
        parts: list[str] = []

        introduction = _normalize_text(
            draft.introduction
        )

        if introduction:
            parts.append(introduction)

        for benefit in draft.benefits:
            cleaned = _normalize_text(benefit)

            existing = {
                item.casefold()
                for item in parts
            }

            if (
                cleaned
                and cleaned.casefold() not in existing
            ):
                parts.append(cleaned)

            if (
                len(" ".join(parts))
                >= self.config.max_meta_description_length
            ):
                break

        if not parts:
            conclusion = _normalize_text(
                draft.conclusion
            )

            if conclusion:
                parts.append(conclusion)

        return _truncate_at_word_boundary(
            " ".join(parts),
            self.config.max_meta_description_length,
        )

    def _build_search_keywords(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
    ) -> tuple[str, ...]:
        candidates: list[str] = [
            context.brand,
            _CATEGORY_KEYWORDS[
                context.product_category
            ],
        ]

        if self.config.include_product_name_keyword:
            candidates.append(
                draft.title
            )

        candidates.extend(
            glossary_match.target
            for glossary_match
            in context.product.glossary_terms
        )

        candidates.extend(
            context.knowledge_keys
        )

        title_tokens = _WORD_RE.findall(
            _normalize_text(draft.title)
        )

        candidates.extend(
            token
            for token in title_tokens
            if (
                len(token) >= 3
                and token.casefold()
                not in _KEYWORD_STOPWORDS
            )
        )

        return self._unique_keywords(
            candidates
        )

    @staticmethod
    def _unique_keywords(
        values: Iterable[str],
    ) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = _normalize_text(value)

            if not cleaned:
                continue

            marker = cleaned.casefold()

            if marker in seen:
                continue

            seen.add(marker)
            result.append(cleaned)

        return tuple(result)