"""Orchestration for Weber grill descriptions with multiple Woo targets.

One Weber source description is translated, formatted, and quality-checked
once. The resulting content can then be planned or applied to one or more
matching WooCommerce products.

Target selection and WooCommerce updating remain delegated to their
specialized modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.descriptions.context_builder import ContextBuilder
from src.descriptions.description_pipeline import PipelineQualityError
from src.descriptions.formatter import ProductFormatter
from src.descriptions.matching.grill_target_selector import (
    select_grill_targets,
)
from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.multi_target_updater import update_targets
from src.descriptions.parser import ProductDescription
from src.descriptions.quality_checker import QualityChecker
from src.descriptions.translator import Translator
from src.descriptions.updater import (
    ProductUpdater,
    UpdateResult,
)


class GrillTargetNotFoundError(RuntimeError):
    """Raised when no WooCommerce target exists for a Weber grill."""


@dataclass(frozen=True, slots=True)
class GrillDescriptionResult:
    """Complete result for one Weber grill description."""

    context: TranslationContext
    draft: TranslationDraft
    formatted: FormattedProduct
    quality: QualityReport
    updates: tuple[UpdateResult, ...]


class GrillDescriptionOrchestrator:
    """Generate one description and send it to all matching Woo targets."""

    def __init__(
        self,
        *,
        translator: Translator,
        context_builder: ContextBuilder | None = None,
        formatter: ProductFormatter | None = None,
        quality_checker: QualityChecker | None = None,
        updater: ProductUpdater | None = None,
    ) -> None:
        if translator is None:
            raise TypeError(
                "translator ir obligāta "
                "GrillDescriptionOrchestrator atkarība."
            )

        self.context_builder = (
            context_builder
            if context_builder is not None
            else ContextBuilder()
        )
        self.translator = translator
        self.formatter = (
            formatter
            if formatter is not None
            else ProductFormatter()
        )
        self.quality_checker = (
            quality_checker
            if quality_checker is not None
            else QualityChecker()
        )
        self.updater = (
            updater
            if updater is not None
            else ProductUpdater()
        )

    def process(
        self,
        *,
        product: ProductDescription,
        woo_products: tuple[dict[str, Any], ...],
    ) -> GrillDescriptionResult:
        """Generate content once and process every matching Woo target."""

        if not isinstance(product, ProductDescription):
            raise TypeError(
                "product jābūt ProductDescription objektam."
            )

        targets = select_grill_targets(
            product=product,
            woo_products=woo_products,
        )

        if not targets:
            raise GrillTargetNotFoundError(
                (
                    f"Produktam {product.title} "
                    "nav atrasts atbilstošs WooCommerce mērķis."
                )
            )

        context = self.context_builder.build(product)

        draft = self.translator.translate(context)

        formatted = self.formatter.format(
            context=context,
            draft=draft,
        )

        quality = self.quality_checker.check(
            context=context,
            draft=draft,
            product=formatted,
        )

        if not quality.passed:
            raise PipelineQualityError(
                (
                    f"Produkta {formatted.sku} apraksts "
                    "neizturēja kvalitātes pārbaudi."
                ),
                quality_report=quality,
            )

        target_skus = tuple(
            str(target.get("sku") or "").strip()
            for target in targets
        )

        updates = update_targets(
            product=formatted,
            quality_report=quality,
            target_skus=target_skus,
            updater=self.updater,
        )

        return GrillDescriptionResult(
            context=context,
            draft=draft,
            formatted=formatted,
            quality=quality,
            updates=updates,
        )