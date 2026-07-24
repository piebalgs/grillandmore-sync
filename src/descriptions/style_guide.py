"""GrillAndMore writing standards for Latvian product descriptions.

This module defines how product content should sound and how it should be
structured. It contains no product data, translation logic or WooCommerce code.

The future translator.py will use these rules when creating Latvian text.
The future quality_checker.py will use the same rules when validating it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence


class SectionId(StrEnum):
    """Stable identifiers for product-description sections."""

    INTRODUCTION = "introduction"
    BENEFITS = "benefits"
    TECHNOLOGIES = "technologies"
    SUITABILITY = "suitability"
    SPECIFICATIONS = "specifications"


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
    severity: str = "warning"


VOICE = VoiceProfile(
    language="lv",
    audience=(
        "Latvijas pircējs, kurš vēlas saprast produkta praktisko pielietojumu, "
        "priekšrocības un tehniskās atšķirības"
    ),
    expertise_level="pieredzējis grilēšanas speciālists",
    tone=(
        "profesionāls",
        "draudzīgs",
        "skaidrs",
        "praktisks",
        "uzticams",
    ),
    marketing_intensity="zema",
    technical_accuracy="augsta",
    seo_priority="vidēja",
)


CORE_PRINCIPLES: tuple[str, ...] = (
    "Saglabā visus ražotāja sniegtos faktus un tehniskos datus.",
    "Neizdomā funkcijas, saderību, priekšrocības vai izmantošanas ierobežojumus.",
    "Vispirms paskaidro ieguvumu klientam, pēc tam nosauc tehnoloģiju.",
    "Tehnoloģiju skaidro tikai tad, ja avota dati ļauj to pamatot.",
    "Lieto dabisku latviešu valodu, nevis burtisku angļu teikuma uzbūvi.",
    "Viena rindkopa apskata vienu galveno domu.",
    "Izvairies no tukšiem reklāmas apgalvojumiem un pārspīlējumiem.",
    "Saglabā Weber preču zīmju un produktu sistēmu nosaukumus.",
    "Nesalīdzini produktu ar citiem modeļiem, ja avotā nav salīdzinājuma datu.",
    "Nesniedz drošības, juridiskus vai uzstādīšanas apgalvojumus bez avota.",
)


DESCRIPTION_SECTIONS: tuple[SectionRule, ...] = (
    SectionRule(
        section_id=SectionId.INTRODUCTION,
        heading="Produkta apraksts",
        purpose=(
            "Divās līdz četrās rindkopās paskaidrot, kas ir produkts, kam tas "
            "paredzēts un kāda ir tā galvenā praktiskā vērtība."
        ),
        required=True,
    ),
    SectionRule(
        section_id=SectionId.BENEFITS,
        heading="Galvenās priekšrocības",
        purpose=(
            "Īsos punktos parādīt būtiskākos klienta ieguvumus, nezaudējot "
            "tehnisko precizitāti."
        ),
        required=True,
        min_items=3,
        max_items=8,
    ),
    SectionRule(
        section_id=SectionId.TECHNOLOGIES,
        heading="Tehnoloģijas un funkcijas",
        purpose=(
            "Izskaidrot svarīgākās ražotāja tehnoloģijas un to praktisko nozīmi."
        ),
        required=False,
        min_items=1,
        max_items=8,
    ),
    SectionRule(
        section_id=SectionId.SUITABILITY,
        heading="Kam šis grils ir piemērots",
        purpose=(
            "Pamatoti raksturot lietošanas situācijas un pircēja vajadzības, "
            "neizdarot pieņēmumus, kurus neatbalsta avota dati."
        ),
        required=False,
    ),
    SectionRule(
        section_id=SectionId.SPECIFICATIONS,
        heading="Tehniskā informācija",
        purpose="Attēlot strukturētos tehniskos datus vienotā un pārskatāmā formā.",
        required=True,
    ),
)


FORBIDDEN_PHRASES: tuple[str, ...] = (
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
)


DISCOURAGED_WORDS: tuple[str, ...] = (
    "vienkārši",
    "protams",
    "acīmredzami",
    "neticami",
    "ārkārtīgi",
    "absolūti",
)


CUSTOMER_BENEFIT_PATTERNS: tuple[str, ...] = (
    "ļauj",
    "palīdz",
    "nodrošina",
    "atvieglo",
    "samazina",
    "uzlabo",
    "padara",
    "saglabā",
    "pasargā",
    "sniedz",
)


HTML_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "h2",
        "h3",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
        "table",
        "tbody",
        "tr",
        "th",
        "td",
    }
)


HTML_SECTION_ORDER: tuple[SectionId, ...] = (
    SectionId.INTRODUCTION,
    SectionId.BENEFITS,
    SectionId.TECHNOLOGIES,
    SectionId.SUITABILITY,
    SectionId.SPECIFICATIONS,
)


MIN_DESCRIPTION_WORDS = 120
TARGET_DESCRIPTION_WORDS = 300
MAX_DESCRIPTION_WORDS = 650

TARGET_SENTENCE_WORDS = 18
MAX_SENTENCE_WORDS = 28

MIN_INTRODUCTION_PARAGRAPHS = 1
MAX_INTRODUCTION_PARAGRAPHS = 3

MIN_BENEFITS = 3
MAX_BENEFITS = 8

MAX_HEADING_WORDS = 6


_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_WORD_PATTERN = re.compile(r"\b[\wĀ-ž]+(?:[-’'][\wĀ-ž]+)*\b", re.UNICODE)
_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*([a-zA-Z0-9]+)")


def count_words(text: str) -> int:
    """Return a practical word count for Latvian product content."""
    return len(_WORD_PATTERN.findall(text))


def split_sentences(text: str) -> list[str]:
    """Split plain text into non-empty sentences."""
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_PATTERN.split(text.strip())
        if sentence.strip()
    ]
def find_overlong_sentences(
    text: str,
    *,
    max_words: int = MAX_SENTENCE_WORDS,
) -> list[str]:
    """Return sentences longer than the configured maximum."""
    return [
        sentence
        for sentence in split_sentences(text)
        if count_words(sentence) > max_words
    ]

def find_forbidden_phrases(text: str) -> list[str]:
    """Return forbidden marketing phrases found in text."""
    lowered = text.casefold()
    return [
        phrase
        for phrase in FORBIDDEN_PHRASES
        if phrase.casefold() in lowered
    ]


def find_discouraged_words(text: str) -> list[str]:
    """Return discouraged filler words found in text."""
    lowered = text.casefold()
    return [
        word
        for word in DISCOURAGED_WORDS
        if re.search(rf"(?<!\w){re.escape(word.casefold())}(?!\w)", lowered)
    ]


def contains_customer_benefit(text: str) -> bool:
    """Check whether text contains at least one benefit-oriented expression."""
    lowered = text.casefold()
    return any(
        re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", lowered)
        for pattern in CUSTOMER_BENEFIT_PATTERNS
    )


def test_sentence_length_maximum_boundary_passes():
    sentence = " ".join(
        [f"vārds{index}" for index in range(28)]
    ) + "."

    draft = make_draft(
        title="Weber grils.",
        introduction=sentence,
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


def find_disallowed_html_tags(html: str) -> list[str]:
    """Return unique HTML tags not allowed by the description standard."""
    tags = {
        match.group(1).casefold()
        for match in _HTML_TAG_PATTERN.finditer(html)
    }
    return sorted(tags - HTML_ALLOWED_TAGS)


def validate_plain_text(text: str) -> list[StyleViolation]:
    """Run basic style checks on generated Latvian plain text."""
    violations: list[StyleViolation] = []
    word_count = count_words(text)

    if word_count < MIN_DESCRIPTION_WORDS:
        violations.append(
            StyleViolation(
                code="description_too_short",
                message=(
                    f"Aprakstā ir {word_count} vārdi; minimums ir "
                    f"{MIN_DESCRIPTION_WORDS}."
                ),
            )
        )

    if word_count > MAX_DESCRIPTION_WORDS:
        violations.append(
            StyleViolation(
                code="description_too_long",
                message=(
                    f"Aprakstā ir {word_count} vārdi; maksimums ir "
                    f"{MAX_DESCRIPTION_WORDS}."
                ),
            )
        )

    for phrase in find_forbidden_phrases(text):
        violations.append(
            StyleViolation(
                code="forbidden_phrase",
                message=f"Atrasta aizliegtā frāze: “{phrase}”.",
                severity="error",
            )
        )

    for sentence in find_overlong_sentences(text):
        violations.append(
            StyleViolation(
                code="sentence_too_long",
                message=(
                    f"Teikums pārsniedz {MAX_SENTENCE_WORDS} vārdus: "
                    f"“{sentence}”"
                ),
            )
        )

    if text.strip() and not contains_customer_benefit(text):
        violations.append(
            StyleViolation(
                code="missing_customer_benefit",
                message=(
                    "Tekstā nav skaidri formulēta praktiskā priekšrocība klientam."
                ),
            )
        )

    return violations


def validate_html(html: str) -> list[StyleViolation]:
    """Run the HTML-specific part of the style validation."""
    return [
        StyleViolation(
            code="disallowed_html_tag",
            message=f"HTML satur neatļautu tagu: <{tag}>.",
            severity="error",
        )
        for tag in find_disallowed_html_tags(html)
    ]


def section_rule(section_id: SectionId | str) -> SectionRule:
    """Return the configured rule for one section."""
    normalized = SectionId(section_id)
    for rule in DESCRIPTION_SECTIONS:
        if rule.section_id == normalized:
            return rule
    raise KeyError(f"Nav definēta sadaļa: {normalized}")


def build_translator_instructions() -> str:
    """Build reusable instructions for the future translator module."""
    principles = "\n".join(f"- {item}" for item in CORE_PRINCIPLES)
    sections = "\n".join(
        f"- {rule.heading}: {rule.purpose}"
        for rule in DESCRIPTION_SECTIONS
    )

    return (
        "Raksti profesionālu produkta aprakstu latviešu valodā.\n\n"
        f"Mērķauditorija: {VOICE.audience}.\n"
        f"Balss: {', '.join(VOICE.tone)}.\n"
        f"Mārketinga intensitāte: {VOICE.marketing_intensity}.\n"
        f"Tehniskā precizitāte: {VOICE.technical_accuracy}.\n\n"
        "Obligātie principi:\n"
        f"{principles}\n\n"
        "Apraksta struktūra:\n"
        f"{sections}\n\n"
        f"Mērķa apjoms: ap {TARGET_DESCRIPTION_WORDS} vārdiem; "
        f"pieļaujamais diapazons ir {MIN_DESCRIPTION_WORDS}–"
        f"{MAX_DESCRIPTION_WORDS} vārdi."
    )


def format_violations(violations: Iterable[StyleViolation]) -> str:
    """Return a readable terminal report."""
    items = list(violations)
    if not items:
        return "PASS: stila pārkāpumi nav atrasti."

    lines = [f"Atrasti pārkāpumi: {len(items)}"]
    for item in items:
        lines.append(
            f"- [{item.severity.upper()}] {item.code}: {item.message}"
        )
    return "\n".join(lines)


def main() -> int:
    """Print a diagnostic preview for terminal testing."""
    print("GrillAndMore stila vadlīnijas")
    print("=" * 32)
    print(f"Valoda: {VOICE.language}")
    print(f"Balss: {', '.join(VOICE.tone)}")
    print(
        f"Apraksta apjoms: {MIN_DESCRIPTION_WORDS}–"
        f"{MAX_DESCRIPTION_WORDS} vārdi"
    )
    print(f"Sadaļas: {len(DESCRIPTION_SECTIONS)}")
    print(f"Aizliegtās frāzes: {len(FORBIDDEN_PHRASES)}")
    print()

    sample = (
        "Šis ir pasaulē labākais un revolucionārs grils. "
        "Nerūsējošā tērauda degļi nodrošina vienmērīgu siltuma sadali."
    )
    print("Pārbaudes piemērs:")
    print(sample)
    print()
    print(format_violations(validate_plain_text(sample)))
    print()

    print("Translatora instrukciju fragments:")
    print("-" * 32)
    print(build_translator_instructions()[:700] + "...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
