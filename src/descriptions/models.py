"""Shared domain models for the GrillAndMore description engine.

This module contains data structures only. Business logic belongs in the
specialized modules such as parser.py, context_builder.py, knowledge_base.py,
translator.py, formatter.py and quality_checker.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Mapping


class SectionId(StrEnum):
    """Stable identifiers for product-description sections."""

    INTRODUCTION = "introduction"
    BENEFITS = "benefits"
    TECHNOLOGIES = "technologies"
    SUITABILITY = "suitability"
    SPECIFICATIONS = "specifications"


class ProductCategory(StrEnum):
    """Deterministically recognized product categories."""

    GAS_GRILL = "gas_grill"
    ELECTRIC_GRILL = "electric_grill"
    CHARCOAL_GRILL = "charcoal_grill"
    PELLET_GRILL = "pellet_grill"
    GRIDDLE = "griddle"
    SMOKER = "smoker"
    ACCESSORY = "accessory"
    REPLACEMENT_PART = "replacement_part"
    OTHER = "other"


class KnowledgeCategory(StrEnum):
    """Supported knowledge-base categories."""

    TECHNOLOGY = "technology"
    MATERIAL = "material"
    ACCESSORY = "accessory"
    WARRANTY = "warranty"
    FUEL = "fuel"
    COOKING_SYSTEM = "cooking_system"
    CLEANING = "cleaning"
    IGNITION = "ignition"
    THERMOMETER = "thermometer"
    COOKING_SURFACE = "cooking_surface"
    SAFETY = "safety"
    COMPATIBILITY = "compatibility"
    CONSTRUCTION = "construction"
    STORAGE = "storage"
    MOBILITY = "mobility"
    OTHER = "other"


class Severity(StrEnum):
    """Severity levels used by validation and quality reports."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TranslationStatus(StrEnum):
    """Lifecycle state of generated product content."""

    PENDING = "pending"
    GENERATED = "generated"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    """The GrillAndMore brand voice."""

    language: str
    audience: str
    expertise_level: str
    tone: tuple[str, ...]
    marketing_intensity: str
    technical_accuracy: str
    seo_priority: str


@dataclass(frozen=True, slots=True)
class SectionRule:
    """Content requirements for one description section."""

    section_id: SectionId
    heading: str
    purpose: str
    required: bool
    min_items: int = 0
    max_items: int | None = None


@dataclass(frozen=True, slots=True)
class StyleViolation:
    """One style-guide validation result."""

    code: str
    message: str
    severity: Severity = Severity.WARNING
    field_name: str | None = None
    value: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    """One verified concept in the GrillAndMore knowledge base."""

    key: str
    category: KnowledgeCategory
    translation: str
    short_description: str
    explanation: str
    customer_benefit: str
    sales_argument: str = ""
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    related_items: tuple[str, ...] = ()
    brands: tuple[str, ...] = ("Weber",)
    source: str = ""
    evidence: tuple[str, ...] = ()
    verified: bool = False
    last_reviewed: date | None = None
    notes: str = ""

    def searchable_text(self) -> str:
        """Return normalized searchable content for this item."""
        parts = (
            self.key,
            self.translation,
            self.short_description,
            self.explanation,
            self.customer_benefit,
            self.sales_argument,
            *self.aliases,
            *self.keywords,
        )
        return " ".join(part for part in parts if part).casefold()


@dataclass(frozen=True, slots=True)
class GlossaryMatch:
    """One glossary term found deterministically in source product data."""

    source: str
    target: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class ProductContext:
    """Facts and deterministic decisions prepared before translation."""

    sku: str
    import_id: str
    brand: str
    product_name: str
    category: ProductCategory
    glossary_terms: tuple[GlossaryMatch, ...] = ()
    knowledge_keys: tuple[str, ...] = ()
    sections: tuple[SectionId, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationContext:
    """Complete structured input supplied to the translation engine."""

    product: ProductContext
    source_language: str = "en"
    target_language: str = "lv"
    source_description: str = ""
    source_sales_arguments: tuple[str, ...] = ()
    source_benefits: tuple[str, ...] = ()
    source_features: tuple[str, ...] = ()
    source_specifications: Mapping[str, str] = field(default_factory=dict)
    translated_specifications: Mapping[str, tuple[str, str]] = field(
        default_factory=dict
    )
    style_instructions: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def sku(self) -> str:
        return self.product.sku

    @property
    def product_name(self) -> str:
        return self.product.product_name

    @property
    def brand(self) -> str:
        return self.product.brand

    @property
    def product_category(self) -> ProductCategory:
        return self.product.category

    @property
    def knowledge_keys(self) -> tuple[str, ...]:
        return self.product.knowledge_keys



@dataclass(frozen=True, slots=True)
class PromptPackage:
    """Deterministic prompts and response contract supplied to an LLM client."""

    system_prompt: str
    user_prompt: str
    response_schema: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationDraft:
    """Structured Latvian content returned by the translation layer."""

    title: str
    introduction: str
    benefits: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    suitability: str = ""
    specifications_summary: str = ""
    conclusion: str = ""
    used_knowledge_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Generated Latvian product content and its processing metadata."""

    sku: str
    product_name: str
    source_description: str
    translated_description: str
    sections: Mapping[SectionId, str] = field(default_factory=dict)
    used_knowledge_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    status: TranslationStatus = TranslationStatus.GENERATED
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FormattedProduct:
    """WooCommerce-ready content created by formatter.py."""

    sku: str
    title: str
    short_description: str
    description_html: str
    meta_description: str = ""
    search_keywords: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """One quality check result."""

    code: str
    message: str
    severity: Severity
    passed: bool
    field_name: str | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Aggregated quality result for one product description."""

    sku: str
    checks: tuple[QualityCheck, ...]
    passed: bool
    error_count: int
    warning_count: int

    @classmethod
    def from_checks(
        cls,
        *,
        sku: str,
        checks: tuple[QualityCheck, ...],
    ) -> "QualityReport":
        """Build a report and calculate summary values."""
        errors = sum(
            1
            for check in checks
            if not check.passed and check.severity == Severity.ERROR
        )
        warnings = sum(
            1
            for check in checks
            if not check.passed and check.severity == Severity.WARNING
        )
        return cls(
            sku=sku,
            checks=checks,
            passed=errors == 0,
            error_count=errors,
            warning_count=warnings,
        )
