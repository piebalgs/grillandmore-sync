"""Deterministic context preparation for product-description translation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from src.descriptions.glossary import (
    PROTECTED_TERMS,
    TERMS,
    translate_specifications,
)
from src.descriptions.knowledge_base import KnowledgeBase, kb
from src.descriptions.models import (
    GlossaryMatch,
    ProductCategory,
    ProductContext,
    SectionId,
    TranslationContext,
)
from src.descriptions.parser import ProductDescription
from src.descriptions.style_guide import build_translator_instructions


_SPACE_PATTERN = re.compile(r"\s+")
_WORD_BOUNDARY = r"(?<![\w-]){term}(?![\w-])"


CATEGORY_BY_SPECIFICATION: dict[str, ProductCategory] = {
    "GAS": ProductCategory.GAS_GRILL,
    "ELECTRIC": ProductCategory.ELECTRIC_GRILL,
    "CHARCOAL": ProductCategory.CHARCOAL_GRILL,
    "PELLET": ProductCategory.PELLET_GRILL,
}


CATEGORY_KEYWORDS: tuple[tuple[ProductCategory, tuple[str, ...]], ...] = (
    (
        ProductCategory.REPLACEMENT_PART,
        (
            "replacement part",
            "spare part",
            "rezerves daļa",
            "burner tube",
            "cooking grate replacement",
        ),
    ),
    (
        ProductCategory.GRIDDLE,
        ("griddle", "plancha", "cepšanas plātne"),
    ),
    (
        ProductCategory.SMOKER,
        ("smoker", "smokehouse", "kūpinātava"),
    ),
    (
        ProductCategory.GAS_GRILL,
        ("gas grill", "gas barbecue", "gāzes grils"),
    ),
    (
        ProductCategory.ELECTRIC_GRILL,
        ("electric grill", "electric barbecue", "elektriskais grils"),
    ),
    (
        ProductCategory.CHARCOAL_GRILL,
        ("charcoal grill", "charcoal barbecue", "kokogļu grils"),
    ),
    (
        ProductCategory.PELLET_GRILL,
        ("pellet grill", "pellet barbecue", "granulu grils"),
    ),
    (
        ProductCategory.ACCESSORY,
        (
            "accessory",
            "cover",
            "brush",
            "tool set",
            "thermometer",
            "probe",
            "basket",
            "rack",
            "rotisserie",
            "piederums",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ContextBuilderConfig:
    """Deterministic context-builder settings."""

    default_brand: str = "Weber"
    include_unverified_knowledge: bool = False
    source_language: str = "en"
    target_language: str = "lv"


class ContextBuilder:
    """Create stable product and translation contexts without AI."""

    def __init__(
        self,
        *,
        knowledge_base: KnowledgeBase = kb,
        config: ContextBuilderConfig | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.config = config or ContextBuilderConfig()

    @staticmethod
    def _normalize(text: str) -> str:
        return _SPACE_PATTERN.sub(" ", str(text).strip())

    def source_text(self, product: ProductDescription) -> str:
        """Return all editorial source text in a fixed, stable order."""
        parts: list[str] = [
            product.title,
            product.title_line_1,
            product.title_line_2,
            product.title_line_3,
            product.source_description,
            *product.sales_arguments,
        ]
        for benefit in product.consumer_benefits:
            parts.extend((benefit.title, benefit.description))
        for feature in product.product_features:
            parts.extend((feature.title, feature.description))
        parts.extend(product.specifications.values())
        return self._normalize(" ".join(part for part in parts if part))

    def detect_brand(self, product: ProductDescription) -> str:
        """Determine the brand without guessing from unrelated wording."""
        raw_brand = self._normalize(
            product.raw.get("Brand", "")
            or product.raw.get("Producer", "")
            or product.raw.get("Manufacturer", "")
        )
        if raw_brand:
            return raw_brand

        source = self.source_text(product)
        if re.search(r"(?<!\w)weber(?!\w)", source, re.IGNORECASE):
            return "Weber"

        return self.config.default_brand

    def detect_category(self, product: ProductDescription) -> ProductCategory:
        """Detect category from structured data first, then known phrases."""
        barbecue_type = self._normalize(
            product.specifications.get("barbecue_type", "")
        ).upper()
        if barbecue_type in CATEGORY_BY_SPECIFICATION:
            return CATEGORY_BY_SPECIFICATION[barbecue_type]

        source = self.source_text(product).casefold()
        for category, keywords in CATEGORY_KEYWORDS:
            if any(keyword.casefold() in source for keyword in keywords):
                return category

        return ProductCategory.OTHER

    def collect_glossary_terms(
        self,
        product: ProductDescription,
    ) -> tuple[GlossaryMatch, ...]:
        """Collect each matching approved term once in glossary order."""
        source = self.source_text(product)
        matches: list[GlossaryMatch] = []
        seen_sources: set[str] = set()

        ordered = sorted(
            TERMS,
            key=lambda item: (-len(item.source), item.source.casefold()),
        )
        for term in ordered:
            normalized_source = term.source.casefold()
            if normalized_source in seen_sources:
                continue

            pattern = re.compile(
                _WORD_BOUNDARY.format(term=re.escape(term.source)),
                re.IGNORECASE,
            )
            if pattern.search(source):
                matches.append(
                    GlossaryMatch(
                        source=term.source,
                        target=term.target,
                        note=term.note,
                    )
                )
                seen_sources.add(normalized_source)

        return tuple(matches)

    def collect_knowledge(
        self,
        product: ProductDescription,
        *,
        brand: str | None = None,
    ) -> tuple[str, ...]:
        """Find explicit knowledge keys or aliases present in source text."""
        source = self.source_text(product)
        selected_brand = brand or self.detect_brand(product)
        found: list[str] = []

        for item in self.knowledge_base.all_items(
            include_unverified=self.config.include_unverified_knowledge
        ):
            if item.brands and not any(
                known_brand.casefold() == selected_brand.casefold()
                for known_brand in item.brands
            ):
                continue

            names = (item.key, *item.aliases)
            if any(
                re.search(
                    _WORD_BOUNDARY.format(term=re.escape(name)),
                    source,
                    re.IGNORECASE,
                )
                for name in names
                if name
            ):
                found.append(item.key)

        return tuple(sorted(set(found), key=str.casefold))

    def choose_sections(
        self,
        product: ProductDescription,
        *,
        knowledge_keys: Iterable[str] = (),
    ) -> tuple[SectionId, ...]:
        """Choose sections solely from available source data."""
        sections: list[SectionId] = [SectionId.INTRODUCTION]

        has_benefits = bool(
            product.sales_arguments
            or product.consumer_benefits
            or product.product_features
        )
        if has_benefits:
            sections.append(SectionId.BENEFITS)

        if tuple(knowledge_keys):
            sections.append(SectionId.TECHNOLOGIES)

        if product.source_description or has_benefits:
            sections.append(SectionId.SUITABILITY)

        if product.specifications:
            sections.append(SectionId.SPECIFICATIONS)

        return tuple(sections)

    def warnings(
        self,
        product: ProductDescription,
        *,
        category: ProductCategory,
        glossary_terms: tuple[GlossaryMatch, ...],
        knowledge_keys: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Return stable editorial warnings in a fixed order."""
        warnings: list[str] = []

        if not product.source_description:
            warnings.append("Nav avota produkta apraksta.")
        if not product.specifications:
            warnings.append("Nav strukturētu tehnisko specifikāciju.")
        if category == ProductCategory.OTHER:
            warnings.append("Produkta kategoriju neizdevās noteikt deterministiski.")
        if glossary_terms and not knowledge_keys:
            protected_found = {
                term.casefold()
                for term in PROTECTED_TERMS
                if re.search(
                    _WORD_BOUNDARY.format(term=re.escape(term)),
                    self.source_text(product),
                    re.IGNORECASE,
                )
            }
            if protected_found:
                warnings.append(
                    "Atrasti aizsargāti termini bez verificēta zināšanu bāzes ieraksta."
                )

        return tuple(warnings)

    def build_product_context(
        self,
        product: ProductDescription,
    ) -> ProductContext:
        """Build deterministic facts and routing decisions."""
        brand = self.detect_brand(product)
        category = self.detect_category(product)
        glossary_terms = self.collect_glossary_terms(product)
        knowledge_keys = self.collect_knowledge(product, brand=brand)
        sections = self.choose_sections(
            product,
            knowledge_keys=knowledge_keys,
        )
        warnings = self.warnings(
            product,
            category=category,
            glossary_terms=glossary_terms,
            knowledge_keys=knowledge_keys,
        )

        return ProductContext(
            sku=product.sku,
            import_id=product.import_id,
            brand=brand,
            product_name=product.title,
            category=category,
            glossary_terms=glossary_terms,
            knowledge_keys=knowledge_keys,
            sections=sections,
            warnings=warnings,
            metadata={
                "source_title_lines": tuple(
                    line
                    for line in (
                        product.title_line_1,
                        product.title_line_2,
                        product.title_line_3,
                    )
                    if line
                ),
                "source_text_length": len(self.source_text(product)),
            },
        )

    def build_translation_context(
        self,
        product: ProductDescription,
    ) -> TranslationContext:
        """Build the complete typed input for translator.py."""
        product_context = self.build_product_context(product)

        benefits = tuple(
            self._normalize(" — ".join(filter(None, (item.title, item.description))))
            for item in product.consumer_benefits
            if item.title or item.description
        )
        features = tuple(
            self._normalize(" — ".join(filter(None, (item.title, item.description))))
            for item in product.product_features
            if item.title or item.description
        )

        return TranslationContext(
            product=product_context,
            source_language=self.config.source_language,
            target_language=self.config.target_language,
            source_description=product.source_description,
            source_sales_arguments=product.sales_arguments,
            source_benefits=benefits,
            source_features=features,
            source_specifications=dict(product.specifications),
            translated_specifications=translate_specifications(
                product.specifications
            ),
            style_instructions=build_translator_instructions(),
            metadata={
                "parser_import_id": product.import_id,
                "raw_field_count": len(product.raw),
            },
        )

    def build(self, product: ProductDescription) -> TranslationContext:
        """Public shorthand for building a complete translation context."""
        return self.build_translation_context(product)


def main() -> int:
    """Run a deterministic self-contained diagnostic example."""
    from src.descriptions.parser import ConsumerBenefit, ProductFeature

    product = ProductDescription(
        sku="DEMO-001",
        import_id="demo",
        title="Weber Genesis gas grill",
        source_description=(
            "Flavorizer Bars and Infinity Ignition support everyday grilling."
        ),
        sales_arguments=("Large cooking area",),
        consumer_benefits=(
            ConsumerBenefit(
                title="Even heat",
                description="Helps cook food consistently.",
            ),
        ),
        product_features=(
            ProductFeature(
                title="Flavorizer Bars",
                description="Cover the burner area.",
            ),
        ),
        specifications={
            "barbecue_type": "GAS",
            "guarantee": "10_L",
            "color": "Black",
        },
        raw={"Brand": "Weber"},
    )

    context = ContextBuilder().build(product)
    print("GrillAndMore context builder")
    print("=" * 31)
    print(f"SKU: {context.sku}")
    print(f"Zīmols: {context.brand}")
    print(f"Kategorija: {context.product_category.value}")
    print(f"Termini: {len(context.product.glossary_terms)}")
    print(f"Zināšanas: {', '.join(context.knowledge_keys) or '-'}")
    print(
        "Sadaļas: "
        + ", ".join(section.value for section in context.product.sections)
    )
    print(f"Brīdinājumi: {len(context.product.warnings)}")
    print("PASS: konteksts izveidots deterministiski.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
