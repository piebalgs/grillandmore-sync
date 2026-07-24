"""Deterministic prompt construction for product-description generation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from src.descriptions.knowledge_base import KnowledgeBase, kb
from src.descriptions.models import (
    KnowledgeItem,
    PromptPackage,
    SectionId,
    TranslationContext,
)
from src.descriptions.style_guide import section_rule


class PromptBuilderError(ValueError):
    """Raised when a valid prompt cannot be built from the supplied context."""


@dataclass(frozen=True, slots=True)
class PromptBuilderConfig:
    """Stable prompt-generation settings."""

    prompt_version: str = "1.0"
    include_source_specifications: bool = True
    include_context_warnings: bool = True
    require_json_only: bool = True


class PromptBuilder:
    """Build provider-neutral prompts from a TranslationContext."""

    def __init__(
        self,
        *,
        knowledge_base: KnowledgeBase = kb,
        config: PromptBuilderConfig | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.config = config or PromptBuilderConfig()

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(str(value).replace("\u00a0", " ").split())

    def _validate_context(self, context: TranslationContext) -> None:
        if not self._clean(context.sku):
            raise PromptBuilderError("TranslationContext trūkst SKU.")
        if not self._clean(context.product_name):
            raise PromptBuilderError("TranslationContext trūkst produkta nosaukuma.")
        if not self._clean(context.target_language):
            raise PromptBuilderError("TranslationContext trūkst mērķa valodas.")
        if not context.product.sections:
            raise PromptBuilderError("TranslationContext nav izvēlēta neviena sadaļa.")

    def collect_knowledge(
        self,
        context: TranslationContext,
    ) -> tuple[KnowledgeItem, ...]:
        """Resolve only knowledge records explicitly selected by ContextBuilder."""
        items: list[KnowledgeItem] = []
        for key in context.knowledge_keys:
            item = self.knowledge_base.find(key)
            if item is not None:
                items.append(item)
        return tuple(items)

    @staticmethod
    def response_schema() -> Mapping[str, Any]:
        """Return the provider-neutral JSON contract expected from the LLM."""
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "title",
                "introduction",
                "benefits",
                "technologies",
                "suitability",
                "specifications_summary",
                "conclusion",
                "used_knowledge_keys",
                "warnings",
            ],
            "properties": {
                "title": {"type": "string"},
                "introduction": {"type": "string"},
                "benefits": {"type": "array", "items": {"type": "string"}},
                "technologies": {"type": "array", "items": {"type": "string"}},
                "suitability": {"type": "string"},
                "specifications_summary": {"type": "string"},
                "conclusion": {"type": "string"},
                "used_knowledge_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        }

    def _section_contract(self, context: TranslationContext) -> list[dict[str, Any]]:
        selected = set(context.product.sections)
        field_by_section = {
            SectionId.INTRODUCTION: "introduction",
            SectionId.BENEFITS: "benefits",
            SectionId.TECHNOLOGIES: "technologies",
            SectionId.SUITABILITY: "suitability",
            SectionId.SPECIFICATIONS: "specifications_summary",
        }
        result: list[dict[str, Any]] = []
        for section_id in SectionId:
            rule = section_rule(section_id)
            result.append(
                {
                    "section_id": section_id.value,
                    "output_field": field_by_section[section_id],
                    "enabled": section_id in selected,
                    "heading": rule.heading,
                    "purpose": rule.purpose,
                    "min_items": rule.min_items,
                    "max_items": rule.max_items,
                }
            )
        return result

    def _glossary_payload(self, context: TranslationContext) -> list[dict[str, str]]:
        return [
            {
                "source": item.source,
                "required_target": item.target,
                "note": item.note,
            }
            for item in context.product.glossary_terms
        ]

    @staticmethod
    def _knowledge_payload(
        items: tuple[KnowledgeItem, ...],
    ) -> list[dict[str, Any]]:
        return [
            {
                "key": item.key,
                "category": item.category.value,
                "translation": item.translation,
                "short_description": item.short_description,
                "explanation": item.explanation,
                "customer_benefit": item.customer_benefit,
                "sales_argument": item.sales_argument,
                "aliases": list(item.aliases),
            }
            for item in items
        ]

    def build_system_prompt(self, context: TranslationContext) -> str:
        """Build stable global instructions, independent of one provider."""
        json_rule = (
            "Atgriez tikai derīgu JSON objektu bez Markdown, koda žogiem vai "
            "papildu komentāriem."
            if self.config.require_json_only
            else "Atgriez rezultātu atbilstoši norādītajai JSON struktūrai."
        )
        return "\n".join(
            (
                "Tu esi profesionāls Latvijas e-komercijas produktu satura redaktors.",
                "Radi precīzu, dabisku un pārliecinošu tekstu latviešu valodā, "
                "izmantojot tikai iesniegtos avota faktus.",
                "",
                "Drošības un precizitātes noteikumi:",
                "- Neizdomā funkcijas, izmērus, materiālus, savietojamību, garantiju "
                "vai citas īpašības.",
                "- Neskaidru vai trūkstošu faktu vietā lieto piesardzīgu formulējumu "
                "vai atstāj attiecīgo lauku tukšu.",
                "- Saglabā modeļu, sēriju un tehnoloģiju nosaukumus tieši tā, kā tie "
                "norādīti avotā vai terminoloģijas sarakstā.",
                "- Obligāti izmanto norādītos terminoloģijas tulkojumus.",
                "- Zināšanu bāzes faktus drīkst izmantot tikai tad, ja tie ir "
                "iekļauti lietotāja ievaddatos.",
                "- Neraksti HTML.",
                f"- {json_rule}",
                "",
                "Stila vadlīnijas:",
                context.style_instructions.strip(),
            )
        ).strip()

    def build_user_payload(
        self,
        context: TranslationContext,
    ) -> Mapping[str, Any]:
        """Build the complete serializable factual payload."""
        knowledge = self.collect_knowledge(context)
        source: dict[str, Any] = {
            "description": context.source_description,
            "sales_arguments": list(context.source_sales_arguments),
            "benefits": list(context.source_benefits),
            "features": list(context.source_features),
            "translated_specifications": {
                key: {"label": value[0], "value": value[1]}
                for key, value in context.translated_specifications.items()
            },
        }
        if self.config.include_source_specifications:
            source["source_specifications"] = dict(context.source_specifications)

        payload: dict[str, Any] = {
            "task": (
                "Izveido strukturētu latviešu produkta apraksta melnrakstu. "
                "Iekļauj tikai tās satura sadaļas, kurām enabled ir true. "
                "Neaktīvo sadaļu laukiem atgriez tukšu tekstu vai tukšu sarakstu."
            ),
            "product": {
                "sku": context.sku,
                "brand": context.brand,
                "source_name": context.product_name,
                "category": context.product_category.value,
                "source_language": context.source_language,
                "target_language": context.target_language,
            },
            "sections": self._section_contract(context),
            "terminology": self._glossary_payload(context),
            "knowledge": self._knowledge_payload(knowledge),
            "source": source,
            "response_requirements": {
                "title": (
                    "Dabisks latviešu produkta nosaukums, saglabājot zīmolu, modeli "
                    "un būtiskos tehniskos apzīmējumus."
                ),
                "introduction": "Īss produkta būtības un galvenā ieguvuma ievads.",
                "benefits": (
                    "Praktiski klienta ieguvumi kā atsevišķi saraksta elementi; "
                    "nedublē vienu domu."
                ),
                "technologies": (
                    "Tikai ievadā dotās verificētās tehnoloģijas un to praktiskā "
                    "nozīme."
                ),
                "suitability": (
                    "Kam un kādam lietojumam produkts ir piemērots, tikai ciktāl to "
                    "pamato avota dati."
                ),
                "specifications_summary": (
                    "Īss tehnisko parametru kopsavilkums; nepārraksti visu tabulu."
                ),
                "conclusion": (
                    "Īss noslēgums bez agresīva pārdošanas spiediena un bez "
                    "nepamatotiem superlatīviem."
                ),
                "used_knowledge_keys": (
                    "Uzskaiti tikai patiešām izmantotās knowledge atslēgas."
                ),
                "warnings": (
                    "Norādi faktu vai datu neskaidrības, kas prasītu redaktora "
                    "pārbaudi."
                ),
            },
            "response_schema": self.response_schema(),
        }
        if self.config.include_context_warnings:
            payload["context_warnings"] = list(context.product.warnings)
        return payload

    def build_user_prompt(self, context: TranslationContext) -> str:
        """Serialize the product payload deterministically as UTF-8 JSON."""
        return json.dumps(
            self.build_user_payload(context),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )

    def build(self, context: TranslationContext) -> PromptPackage:
        """Build the complete provider-neutral prompt package."""
        self._validate_context(context)
        knowledge = self.collect_knowledge(context)
        return PromptPackage(
            system_prompt=self.build_system_prompt(context),
            user_prompt=self.build_user_prompt(context),
            response_schema=self.response_schema(),
            metadata={
                "prompt_version": self.config.prompt_version,
                "sku": context.sku,
                "category": context.product_category.value,
                "section_count": len(context.product.sections),
                "glossary_term_count": len(context.product.glossary_terms),
                "knowledge_item_count": len(knowledge),
            },
        )


def main() -> int:
    """Run a deterministic diagnostic preview."""
    from src.descriptions.context_builder import ContextBuilder
    from src.descriptions.parser import ProductDescription

    product = ProductDescription(
        sku="DEMO-001",
        import_id="demo",
        title="Weber gas grill",
        source_description="Compact gas grill with porcelain-enamelled cooking grate.",
        sales_arguments=("Compact design",),
        specifications={"barbecue_type": "GAS", "color": "Black"},
        raw={"Brand": "Weber"},
    )
    package = PromptBuilder().build(ContextBuilder().build(product))
    print("GrillAndMore prompt builder")
    print("=" * 28)
    print(f"SKU: {package.metadata['sku']}")
    print(f"Prompta versija: {package.metadata['prompt_version']}")
    print(f"Sistēmas prompta garums: {len(package.system_prompt)}")
    print(f"Lietotāja prompta garums: {len(package.user_prompt)}")
    print("PASS: prompts izveidots deterministiski.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
