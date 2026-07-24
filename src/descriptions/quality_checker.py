"""Deterministic quality validation for generated product descriptions.

The quality checker validates structured translation output and the final
WooCommerce-ready product without calling an LLM or modifying product data.

Pipeline:

    TranslationContext
            +
    TranslationDraft
            +
    FormattedProduct
            |
            v
      QualityChecker
            |
            v
       QualityReport

Every validation rule is independent and can be tested or extended without
changing the checker itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Iterable, Protocol, Sequence

from src.descriptions.models import (
    FormattedProduct,
    QualityCheck,
    QualityReport,
    SectionId,
    Severity,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.style_guide import (
    MAX_BENEFITS,
    MAX_DESCRIPTION_WORDS,
    MIN_BENEFITS,
    MIN_DESCRIPTION_WORDS,
    count_words,
    find_discouraged_words,
    find_disallowed_html_tags,
    find_forbidden_phrases,
    find_overlong_sentences,
)


QUALITY_CHECKER_VERSION = "1.0"


class QualityCheckerError(ValueError):
    """Raised when quality checking cannot be performed."""


@dataclass(frozen=True, slots=True)
class QualityCheckerConfig:
    """Configuration for deterministic quality rules."""

    min_title_length: int = 5
    max_title_length: int = 180

    min_short_description_words: int = 8
    max_short_description_words: int = 80

    min_meta_description_length: int = 70
    max_meta_description_length: int = 160

    min_search_keywords: int = 2
    max_search_keywords: int = 20

    require_brand_in_title: bool = True
    require_meta_description: bool = True
    require_search_keywords: bool = True

    check_source_numbers: bool = True
    check_glossary_terms: bool = True
    check_discouraged_words: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values."""

        integer_fields = {
            "min_title_length": self.min_title_length,
            "max_title_length": self.max_title_length,
            "min_short_description_words": self.min_short_description_words,
            "max_short_description_words": self.max_short_description_words,
            "min_meta_description_length": self.min_meta_description_length,
            "max_meta_description_length": self.max_meta_description_length,
            "min_search_keywords": self.min_search_keywords,
            "max_search_keywords": self.max_search_keywords,
        }

        for field_name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    f"{field_name} jābūt veselam skaitlim."
                )

            if value < 0:
                raise ValueError(
                    f"{field_name} nedrīkst būt negatīvs."
                )

        ranges = (
            (
                "title",
                self.min_title_length,
                self.max_title_length,
            ),
            (
                "short_description",
                self.min_short_description_words,
                self.max_short_description_words,
            ),
            (
                "meta_description",
                self.min_meta_description_length,
                self.max_meta_description_length,
            ),
            (
                "search_keywords",
                self.min_search_keywords,
                self.max_search_keywords,
            ),
        )

        for range_name, minimum, maximum in ranges:
            if minimum > maximum:
                raise ValueError(
                    f"{range_name}: minimums nedrīkst pārsniegt maksimumu."
                )


@dataclass(frozen=True, slots=True)
class QualityInput:
    """Complete immutable input supplied to every quality rule."""

    context: TranslationContext
    draft: TranslationDraft
    product: FormattedProduct
    config: QualityCheckerConfig


class QualityRule(Protocol):
    """Interface implemented by every deterministic quality rule."""

    code: str

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        """Evaluate one rule and return one or more checks."""


class _PlainTextExtractor(HTMLParser):
    """Extract visible text and record basic HTML structure errors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.open_tags: list[str] = []
        self.structure_errors: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs

        normalized = tag.casefold()

        if normalized not in {
            "br",
            "hr",
            "img",
            "input",
            "meta",
            "link",
        }:
            self.open_tags.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()

        if normalized not in self.open_tags:
            self.structure_errors.append(
                f"Aizverošajam tagam </{normalized}> nav atverošā taga."
            )
            return

        if self.open_tags[-1] != normalized:
            expected = self.open_tags[-1]
            self.structure_errors.append(
                f"Nepareiza tagu secība: gaidīts </{expected}>, "
                f"saņemts </{normalized}>."
            )
            self.open_tags.remove(normalized)
            return

        self.open_tags.pop()

    def handle_data(self, data: str) -> None:
        normalized = _normalize_whitespace(data)

        if normalized:
            self.text_parts.append(normalized)

    def plain_text(self) -> str:
        """Return normalized visible text."""

        return " ".join(self.text_parts).strip()


def _normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace deterministically."""

    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_comparison(value: str) -> str:
    """Normalize text for case-insensitive duplicate checks."""

    value = _normalize_whitespace(value).casefold()
    value = re.sub(r"[^\wĀ-ž]+", " ", value, flags=re.UNICODE)
    return _normalize_whitespace(value)


def _plain_text(html: str) -> tuple[str, tuple[str, ...]]:
    """Extract text and HTML structure errors."""

    parser = _PlainTextExtractor()

    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        return "", (f"HTML parsēšanas kļūda: {exc}",)

    errors = list(parser.structure_errors)

    for tag in reversed(parser.open_tags):
        errors.append(f"Tagam <{tag}> nav aizverošā taga.")

    return parser.plain_text(), tuple(errors)


def _make_check(
    *,
    code: str,
    message: str,
    severity: Severity,
    passed: bool,
    field_name: str | None = None,
) -> QualityCheck:
    """Create one quality result consistently."""

    return QualityCheck(
        code=code,
        message=message,
        severity=severity,
        passed=passed,
        field_name=field_name,
    )


def _all_draft_text(draft: TranslationDraft) -> str:
    """Return all generated draft text as one normalized string."""

    parts: list[str] = [
        draft.title,
        draft.introduction,
        *draft.benefits,
        *draft.technologies,
        draft.suitability,
        draft.specifications_summary,
        draft.conclusion,
    ]

    return _normalize_whitespace(
        " ".join(part for part in parts if part)
    )


def _source_text(context: TranslationContext) -> str:
    """Return all available source facts as searchable text."""

    specification_parts: list[str] = []

    for source_key, source_value in context.source_specifications.items():
        specification_parts.extend(
            (
                str(source_key),
                str(source_value),
            )
        )

    for source_key, translated_value in (
        context.translated_specifications.items()
    ):
        label, value = translated_value
        specification_parts.extend(
            (
                str(source_key),
                str(label),
                str(value),
            )
        )

    parts = [
        context.product_name,
        context.brand,
        context.source_description,
        *context.source_sales_arguments,
        *context.source_benefits,
        *context.source_features,
        *specification_parts,
    ]

    return _normalize_whitespace(
        " ".join(part for part in parts if part)
    )


def _extract_numbers(text: str) -> set[str]:
    """Extract normalized numeric values from text."""

    results: set[str] = set()

    for match in re.findall(
        r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)?",
        text,
        flags=re.IGNORECASE,
    ):
        normalized = re.sub(r"\s+", "", match)
        normalized = normalized.replace(",", ".")
        normalized = normalized.replace("×", "x")
        results.add(normalized.casefold())

    return results


class RequiredFieldsRule:
    """Ensure mandatory content fields are present."""

    code = "required_fields"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        fields = {
            "sku": quality_input.product.sku,
            "title": quality_input.product.title,
            "short_description": quality_input.product.short_description,
            "description_html": quality_input.product.description_html,
        }

        checks: list[QualityCheck] = []

        for field_name, value in fields.items():
            passed = bool(_normalize_whitespace(value))

            checks.append(
                _make_check(
                    code=f"{self.code}.{field_name}",
                    message=(
                        f"Lauks “{field_name}” ir aizpildīts."
                        if passed
                        else f"Obligātais lauks “{field_name}” ir tukšs."
                    ),
                    severity=Severity.ERROR,
                    passed=passed,
                    field_name=field_name,
                )
            )

        if quality_input.config.require_meta_description:
            value = quality_input.product.meta_description
            passed = bool(_normalize_whitespace(value))

            checks.append(
                _make_check(
                    code=f"{self.code}.meta_description",
                    message=(
                        "Meta apraksts ir aizpildīts."
                        if passed
                        else "Obligātais meta apraksts ir tukšs."
                    ),
                    severity=Severity.ERROR,
                    passed=passed,
                    field_name="meta_description",
                )
            )

        return tuple(checks)


class IdentityRule:
    """Validate that all pipeline objects belong to the same product."""

    code = "identity"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        context_sku = _normalize_whitespace(quality_input.context.sku)
        product_sku = _normalize_whitespace(quality_input.product.sku)

        passed = bool(context_sku) and context_sku == product_sku

        return (
            _make_check(
                code=f"{self.code}.sku_match",
                message=(
                    f"SKU sakrīt: {product_sku}."
                    if passed
                    else (
                        "Konteksta un formatētā produkta SKU nesakrīt: "
                        f"“{context_sku}” pret “{product_sku}”."
                    )
                ),
                severity=Severity.ERROR,
                passed=passed,
                field_name="sku",
            ),
        )


class TitleRule:
    """Validate product title length and brand presence."""

    code = "title"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        title = _normalize_whitespace(quality_input.product.title)
        config = quality_input.config
        checks: list[QualityCheck] = []

        length = len(title)

        length_passed = (
            config.min_title_length
            <= length
            <= config.max_title_length
        )

        checks.append(
            _make_check(
                code=f"{self.code}.length",
                message=(
                    f"Virsraksta garums ir pieļaujams: {length} rakstzīmes."
                    if length_passed
                    else (
                        f"Virsrakstā ir {length} rakstzīmes; "
                        f"pieļaujams {config.min_title_length}–"
                        f"{config.max_title_length}."
                    )
                ),
                severity=Severity.ERROR,
                passed=length_passed,
                field_name="title",
            )
        )

        if config.require_brand_in_title:
            brand = _normalize_whitespace(quality_input.context.brand)

            brand_passed = (
                not brand
                or brand.casefold() in title.casefold()
            )

            checks.append(
                _make_check(
                    code=f"{self.code}.brand",
                    message=(
                        "Produkta zīmols ir ietverts virsrakstā."
                        if brand_passed
                        else (
                            f"Virsrakstā nav ietverts zīmols “{brand}”."
                        )
                    ),
                    severity=Severity.WARNING,
                    passed=brand_passed,
                    field_name="title",
                )
            )

        return tuple(checks)


class DescriptionLengthRule:
    """Validate visible full-description length."""

    code = "description_length"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        plain_text, _ = _plain_text(
            quality_input.product.description_html
        )
        word_count = count_words(plain_text)

        passed = (
            MIN_DESCRIPTION_WORDS
            <= word_count
            <= MAX_DESCRIPTION_WORDS
        )

        return (
            _make_check(
                code=self.code,
                message=(
                    f"Aprakstā ir {word_count} vārdi."
                    if passed
                    else (
                        f"Aprakstā ir {word_count} vārdi; pieļaujamais "
                        f"diapazons ir {MIN_DESCRIPTION_WORDS}–"
                        f"{MAX_DESCRIPTION_WORDS}."
                    )
                ),
                severity=Severity.WARNING,
                passed=passed,
                field_name="description_html",
            ),
        )


class ShortDescriptionRule:
    """Validate short-description word count."""

    code = "short_description"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        plain_text, _ = _plain_text(
            quality_input.product.short_description
        )
        word_count = count_words(plain_text)
        config = quality_input.config

        passed = (
            config.min_short_description_words
            <= word_count
            <= config.max_short_description_words
        )

        return (
            _make_check(
                code=f"{self.code}.length",
                message=(
                    f"Īsajā aprakstā ir {word_count} vārdi."
                    if passed
                    else (
                        f"Īsajā aprakstā ir {word_count} vārdi; "
                        f"pieļaujams {config.min_short_description_words}–"
                        f"{config.max_short_description_words}."
                    )
                ),
                severity=Severity.WARNING,
                passed=passed,
                field_name="short_description",
            ),
        )


class HTMLRule:
    """Validate allowed tags and basic HTML structure."""

    code = "html"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        html = quality_input.product.description_html
        checks: list[QualityCheck] = []

        disallowed_tags = find_disallowed_html_tags(html)

        checks.append(
            _make_check(
                code=f"{self.code}.allowed_tags",
                message=(
                    "HTML satur tikai atļautos tagus."
                    if not disallowed_tags
                    else (
                        "HTML satur neatļautus tagus: "
                        + ", ".join(
                            f"<{tag}>" for tag in disallowed_tags
                        )
                        + "."
                    )
                ),
                severity=Severity.ERROR,
                passed=not disallowed_tags,
                field_name="description_html",
            )
        )

        _, structure_errors = _plain_text(html)

        checks.append(
            _make_check(
                code=f"{self.code}.structure",
                message=(
                    "HTML tagu struktūra ir korekta."
                    if not structure_errors
                    else " ".join(structure_errors)
                ),
                severity=Severity.ERROR,
                passed=not structure_errors,
                field_name="description_html",
            )
        )

        return tuple(checks)


class MarketingLanguageRule:
    """Detect forbidden and discouraged marketing wording."""

    code = "marketing_language"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        text = _all_draft_text(quality_input.draft)
        checks: list[QualityCheck] = []

        forbidden = find_forbidden_phrases(text)

        checks.append(
            _make_check(
                code=f"{self.code}.forbidden_phrases",
                message=(
                    "Aizliegtas reklāmas frāzes nav atrastas."
                    if not forbidden
                    else (
                        "Atrastas aizliegtas reklāmas frāzes: "
                        + ", ".join(f"“{item}”" for item in forbidden)
                        + "."
                    )
                ),
                severity=Severity.ERROR,
                passed=not forbidden,
                field_name="description_html",
            )
        )

        if quality_input.config.check_discouraged_words:
            discouraged = find_discouraged_words(text)

            checks.append(
                _make_check(
                    code=f"{self.code}.discouraged_words",
                    message=(
                        "Nevēlami aizpildījuma vārdi nav atrasti."
                        if not discouraged
                        else (
                            "Atrasti nevēlami vārdi: "
                            + ", ".join(
                                f"“{item}”" for item in discouraged
                            )
                            + "."
                        )
                    ),
                    severity=Severity.WARNING,
                    passed=not discouraged,
                    field_name="description_html",
                )
            )

        return tuple(checks)


class SentenceLengthRule:
    """Detect sentences that are longer than the style limit."""

    code = "sentence_length"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        text = _all_draft_text(quality_input.draft)
        overlong = find_overlong_sentences(text)

        return (
            _make_check(
                code=self.code,
                message=(
                    "Pārāk gari teikumi nav atrasti."
                    if not overlong
                    else (
                        f"Atrasti {len(overlong)} pārāk gari teikumi. "
                        f"Pirmais: “{overlong[0]}”"
                    )
                ),
                severity=Severity.WARNING,
                passed=not overlong,
                field_name="description_html",
            ),
        )


class SectionRule:
    """Validate active sections and benefit counts."""

    code = "sections"

    _FIELD_MAP = {
        SectionId.INTRODUCTION: "introduction",
        SectionId.BENEFITS: "benefits",
        SectionId.TECHNOLOGIES: "technologies",
        SectionId.SUITABILITY: "suitability",
        SectionId.SPECIFICATIONS: "specifications_summary",
    }

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        active_sections = set(quality_input.context.product.sections)
        draft = quality_input.draft
        checks: list[QualityCheck] = []

        for section_id, field_name in self._FIELD_MAP.items():
            value = getattr(draft, field_name)

            if isinstance(value, tuple):
                has_content = any(
                    _normalize_whitespace(item)
                    for item in value
                )
            else:
                has_content = bool(_normalize_whitespace(value))

            if section_id in active_sections:
                checks.append(
                    _make_check(
                        code=f"{self.code}.{section_id.value}.present",
                        message=(
                            f"Aktīvā sadaļa “{section_id.value}” "
                            "ir aizpildīta."
                            if has_content
                            else (
                                f"Aktīvā sadaļa “{section_id.value}” "
                                "nav aizpildīta."
                            )
                        ),
                        severity=Severity.ERROR,
                        passed=has_content,
                        field_name=field_name,
                    )
                )
            else:
                checks.append(
                    _make_check(
                        code=f"{self.code}.{section_id.value}.inactive",
                        message=(
                            f"Neaktīvā sadaļa “{section_id.value}” ir tukša."
                            if not has_content
                            else (
                                f"Neaktīvā sadaļa “{section_id.value}” "
                                "satur ģenerētu tekstu."
                            )
                        ),
                        severity=Severity.WARNING,
                        passed=not has_content,
                        field_name=field_name,
                    )
                )

        benefit_count = len(
            tuple(
                item
                for item in draft.benefits
                if _normalize_whitespace(item)
            )
        )

        benefits_active = SectionId.BENEFITS in active_sections

        count_passed = (
            not benefits_active
            or MIN_BENEFITS <= benefit_count <= MAX_BENEFITS
        )

        checks.append(
            _make_check(
                code=f"{self.code}.benefit_count",
                message=(
                    f"Priekšrocību skaits ir pieļaujams: {benefit_count}."
                    if count_passed
                    else (
                        f"Priekšrocību skaits ir {benefit_count}; "
                        f"pieļaujams {MIN_BENEFITS}–{MAX_BENEFITS}."
                    )
                ),
                severity=Severity.WARNING,
                passed=count_passed,
                field_name="benefits",
            )
        )

        return tuple(checks)


class DuplicateContentRule:
    """Detect duplicate list entries and repeated sections."""

    code = "duplicates"

    @staticmethod
    def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
        seen: dict[str, str] = {}
        duplicates: list[str] = []

        for value in values:
            normalized = _normalize_comparison(value)

            if not normalized:
                continue

            if normalized in seen:
                original = seen[normalized]

                if original not in duplicates:
                    duplicates.append(original)
            else:
                seen[normalized] = _normalize_whitespace(value)

        return tuple(duplicates)

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        draft = quality_input.draft
        checks: list[QualityCheck] = []

        groups = {
            "benefits": draft.benefits,
            "technologies": draft.technologies,
            "search_keywords": quality_input.product.search_keywords,
        }

        for field_name, values in groups.items():
            duplicates = self._duplicates(values)

            checks.append(
                _make_check(
                    code=f"{self.code}.{field_name}",
                    message=(
                        f"Laukā “{field_name}” dublikāti nav atrasti."
                        if not duplicates
                        else (
                            f"Laukā “{field_name}” atrasti dublikāti: "
                            + ", ".join(
                                f"“{item}”" for item in duplicates
                            )
                            + "."
                        )
                    ),
                    severity=Severity.WARNING,
                    passed=not duplicates,
                    field_name=field_name,
                )
            )

        section_values = (
            draft.introduction,
            draft.suitability,
            draft.specifications_summary,
            draft.conclusion,
        )
        duplicate_sections = self._duplicates(section_values)

        checks.append(
            _make_check(
                code=f"{self.code}.sections",
                message=(
                    "Savstarpēji dublētas teksta sadaļas nav atrastas."
                    if not duplicate_sections
                    else "Divās vai vairākās sadaļās atkārtojas vienāds teksts."
                ),
                severity=Severity.WARNING,
                passed=not duplicate_sections,
                field_name="description_html",
            )
        )

        return tuple(checks)


class KnowledgeRule:
    """Ensure the draft uses only context-approved knowledge keys."""

    code = "knowledge"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        allowed = {
            _normalize_comparison(key)
            for key in quality_input.context.knowledge_keys
            if _normalize_whitespace(key)
        }
        used = {
            _normalize_comparison(key)
            for key in quality_input.draft.used_knowledge_keys
            if _normalize_whitespace(key)
        }

        unsupported = sorted(used - allowed)
        passed = not unsupported

        return (
            _make_check(
                code=f"{self.code}.allowed_keys",
                message=(
                    "Izmantotas tikai kontekstā atļautās zināšanu atslēgas."
                    if passed
                    else (
                        "Izmantotas neatļautas zināšanu atslēgas: "
                        + ", ".join(f"“{item}”" for item in unsupported)
                        + "."
                    )
                ),
                severity=Severity.ERROR,
                passed=passed,
                field_name="used_knowledge_keys",
            ),
        )


class GlossaryRule:
    """Ensure required glossary translations occur in generated content."""

    code = "glossary"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        if not quality_input.config.check_glossary_terms:
            return ()

        text = _normalize_comparison(
            _all_draft_text(quality_input.draft)
        )

        checks: list[QualityCheck] = []

        for glossary_match in quality_input.context.product.glossary_terms:
            target = _normalize_whitespace(glossary_match.target)
            normalized_target = _normalize_comparison(target)

            passed = (
                not normalized_target
                or normalized_target in text
            )

            checks.append(
                _make_check(
                    code=f"{self.code}.required_term",
                    message=(
                        f"Terminoloģija “{target}” ir izmantota."
                        if passed
                        else (
                            f"Obligātais terminoloģijas variants "
                            f"“{target}” tekstā nav atrasts."
                        )
                    ),
                    severity=Severity.WARNING,
                    passed=passed,
                    field_name="description_html",
                )
            )

        return tuple(checks)


class SourceNumbersRule:
    """Warn when generated numeric facts are absent from source data."""

    code = "source_numbers"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        if not quality_input.config.check_source_numbers:
            return ()

        source_numbers = _extract_numbers(
            _source_text(quality_input.context)
        )
        generated_numbers = _extract_numbers(
            _all_draft_text(quality_input.draft)
        )

        unsupported = sorted(generated_numbers - source_numbers)
        passed = not unsupported

        return (
            _make_check(
                code=self.code,
                message=(
                    "Visi ģenerētie skaitliskie dati ir atrodami avota datos."
                    if passed
                    else (
                        "Ģenerētajā tekstā atrasti skaitļi, kas nav "
                        "atrodami avota datos: "
                        + ", ".join(unsupported)
                        + "."
                    )
                ),
                severity=Severity.WARNING,
                passed=passed,
                field_name="description_html",
            ),
        )


class MetaDescriptionRule:
    """Validate SEO meta-description length and content."""

    code = "meta_description"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        value = _normalize_whitespace(
            quality_input.product.meta_description
        )
        config = quality_input.config

        if not value and not config.require_meta_description:
            return ()

        length = len(value)
        length_passed = (
            config.min_meta_description_length
            <= length
            <= config.max_meta_description_length
        )

        forbidden = find_forbidden_phrases(value)

        return (
            _make_check(
                code=f"{self.code}.length",
                message=(
                    f"Meta aprakstā ir {length} rakstzīmes."
                    if length_passed
                    else (
                        f"Meta aprakstā ir {length} rakstzīmes; "
                        f"pieļaujams {config.min_meta_description_length}–"
                        f"{config.max_meta_description_length}."
                    )
                ),
                severity=Severity.WARNING,
                passed=length_passed,
                field_name="meta_description",
            ),
            _make_check(
                code=f"{self.code}.forbidden_phrases",
                message=(
                    "Meta aprakstā nav aizliegtu reklāmas frāžu."
                    if not forbidden
                    else (
                        "Meta aprakstā atrastas aizliegtas frāzes: "
                        + ", ".join(
                            f"“{item}”" for item in forbidden
                        )
                        + "."
                    )
                ),
                severity=Severity.ERROR,
                passed=not forbidden,
                field_name="meta_description",
            ),
        )


class SearchKeywordsRule:
    """Validate search keyword count and empty values."""

    code = "search_keywords"

    def evaluate(
        self,
        quality_input: QualityInput,
    ) -> tuple[QualityCheck, ...]:
        config = quality_input.config
        raw_keywords = quality_input.product.search_keywords

        keywords = tuple(
            _normalize_whitespace(keyword)
            for keyword in raw_keywords
            if _normalize_whitespace(keyword)
        )

        if not keywords and not config.require_search_keywords:
            return ()

        count = len(keywords)
        count_passed = (
            config.min_search_keywords
            <= count
            <= config.max_search_keywords
        )

        empty_passed = len(keywords) == len(raw_keywords)

        return (
            _make_check(
                code=f"{self.code}.count",
                message=(
                    f"Meklēšanas atslēgvārdu skaits ir {count}."
                    if count_passed
                    else (
                        f"Meklēšanas atslēgvārdu skaits ir {count}; "
                        f"pieļaujams {config.min_search_keywords}–"
                        f"{config.max_search_keywords}."
                    )
                ),
                severity=Severity.WARNING,
                passed=count_passed,
                field_name="search_keywords",
            ),
            _make_check(
                code=f"{self.code}.empty_values",
                message=(
                    "Tukši meklēšanas atslēgvārdi nav atrasti."
                    if empty_passed
                    else "Meklēšanas atslēgvārdu sarakstā ir tukšas vērtības."
                ),
                severity=Severity.WARNING,
                passed=empty_passed,
                field_name="search_keywords",
            ),
        )


DEFAULT_RULES: tuple[QualityRule, ...] = (
    RequiredFieldsRule(),
    IdentityRule(),
    TitleRule(),
    DescriptionLengthRule(),
    ShortDescriptionRule(),
    HTMLRule(),
    MarketingLanguageRule(),
    SentenceLengthRule(),
    SectionRule(),
    DuplicateContentRule(),
    KnowledgeRule(),
    GlossaryRule(),
    SourceNumbersRule(),
    MetaDescriptionRule(),
    SearchKeywordsRule(),
)


class QualityChecker:
    """Run deterministic validation rules and build a quality report."""

    def __init__(
        self,
        *,
        config: QualityCheckerConfig | None = None,
        rules: Sequence[QualityRule] | None = None,
    ) -> None:
        self._config = config or QualityCheckerConfig()
        self._rules = tuple(
            DEFAULT_RULES if rules is None else rules
        )

        self._validate_rules()

    @property
    def config(self) -> QualityCheckerConfig:
        """Return immutable checker configuration."""

        return self._config

    @property
    def rules(self) -> tuple[QualityRule, ...]:
        """Return the active validation rules."""

        return self._rules

    def check(
        self,
        *,
        context: TranslationContext,
        draft: TranslationDraft,
        product: FormattedProduct,
    ) -> QualityReport:
        """Validate one generated product and return its complete report."""

        self._validate_input(
            context=context,
            draft=draft,
            product=product,
        )

        quality_input = QualityInput(
            context=context,
            draft=draft,
            product=product,
            config=self._config,
        )

        checks: list[QualityCheck] = []

        for rule in self._rules:
            results = rule.evaluate(quality_input)

            for result in results:
                if not isinstance(result, QualityCheck):
                    raise QualityCheckerError(
                        f"Noteikums “{rule.code}” neatgrieza QualityCheck."
                    )

                checks.append(result)

        return QualityReport.from_checks(
            sku=product.sku,
            checks=tuple(checks),
        )

    def _validate_rules(self) -> None:
        """Validate rule collection at checker construction time."""

        seen_codes: set[str] = set()

        for rule in self._rules:
            code = _normalize_whitespace(
                getattr(rule, "code", "")
            )

            if not code:
                raise QualityCheckerError(
                    "Katram kvalitātes noteikumam jābūt kodam."
                )

            if code in seen_codes:
                raise QualityCheckerError(
                    f"Dublēts kvalitātes noteikuma kods: “{code}”."
                )

            if not callable(getattr(rule, "evaluate", None)):
                raise QualityCheckerError(
                    f"Noteikumam “{code}” nav evaluate() metodes."
                )

            seen_codes.add(code)

    @staticmethod
    def _validate_input(
        *,
        context: TranslationContext,
        draft: TranslationDraft,
        product: FormattedProduct,
    ) -> None:
        """Reject invalid pipeline objects before running rules."""

        if not isinstance(context, TranslationContext):
            raise TypeError(
                "context jābūt TranslationContext objektam."
            )

        if not isinstance(draft, TranslationDraft):
            raise TypeError(
                "draft jābūt TranslationDraft objektam."
            )

        if not isinstance(product, FormattedProduct):
            raise TypeError(
                "product jābūt FormattedProduct objektam."
            )


def format_quality_report(report: QualityReport) -> str:
    """Return a deterministic human-readable terminal report."""

    if not isinstance(report, QualityReport):
        raise TypeError(
            "report jābūt QualityReport objektam."
        )

    status = "PASS" if report.passed else "FAIL"

    lines = [
        f"{status}: SKU {report.sku}",
        (
            f"Kļūdas: {report.error_count}, "
            f"brīdinājumi: {report.warning_count}, "
            f"pārbaudes: {len(report.checks)}"
        ),
    ]

    failed_checks = tuple(
        check
        for check in report.checks
        if not check.passed
    )

    if not failed_checks:
        lines.append("Kvalitātes pārkāpumi nav atrasti.")
        return "\n".join(lines)

    severity_order = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.INFO: 2,
    }

    ordered_checks = sorted(
        failed_checks,
        key=lambda check: (
            severity_order[check.severity],
            check.code,
            check.field_name or "",
        ),
    )

    for check in ordered_checks:
        field = (
            f" [{check.field_name}]"
            if check.field_name
            else ""
        )

        lines.append(
            f"- {check.severity.value.upper()}{field} "
            f"{check.code}: {check.message}"
        )

    return "\n".join(lines)

