"""Product-description generation pipeline.

This module coordinates the complete product-description workflow:

    ProductDescription
            |
            v
      ContextBuilder
            |
            v
        Translator
            |
            v
     ProductFormatter
            |
            v
      QualityChecker
            |
            v
      ProductUpdater

The pipeline intentionally contains no translation, formatting,
quality-control, or WooCommerce business logic. Those responsibilities
belong to the individual components.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.descriptions.context_builder import ContextBuilder
from src.descriptions.formatter import ProductFormatter
from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
    TranslationContext,
    TranslationDraft,
)
from src.descriptions.parser import ProductDescription
from src.descriptions.quality_checker import QualityChecker
from src.descriptions.translator import Translator
from src.descriptions.updater import (
    ProductUpdater,
    UpdateResult,
)


PIPELINE_VERSION = "1.0"


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot continue safely."""


class PipelineQualityError(PipelineError):
    """Raised when generated content fails the quality gate."""

    def __init__(
        self,
        message: str,
        *,
        quality_report: QualityReport,
    ) -> None:
        super().__init__(message)
        self.quality_report = quality_report


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Execution settings for DescriptionPipeline.

    Attributes:
        fail_on_quality_errors:
            When True, the pipeline stops before ProductUpdater if the
            quality report does not pass.

            When False, the quality report is passed to ProductUpdater,
            which may still block the update according to its own
            configuration.
    """

    fail_on_quality_errors: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.fail_on_quality_errors, bool):
            raise TypeError(
                "fail_on_quality_errors jābūt bool vērtībai."
            )


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Complete immutable result of one pipeline execution."""

    context: TranslationContext
    draft: TranslationDraft
    formatted: FormattedProduct
    quality: QualityReport
    update: UpdateResult

    @property
    def success(self) -> bool:
        """Return True when quality and update stages both succeeded."""

        return (
            self.quality.passed
            and self.update.success
        )

    @property
    def sku(self) -> str:
        """Return the processed product SKU."""

        return self.formatted.sku


class DescriptionPipeline:
    """Coordinate all product-description generation components.

    Translator is a required dependency because it needs a configured
    LLM client. The pipeline must not decide which LLM provider, model,
    credentials, or retry policy should be used.

    Other components can be supplied explicitly for testing or custom
    configuration. When omitted, their default implementations are used.
    """

    def __init__(
        self,
        *,
        translator: Translator,
        context_builder: ContextBuilder | None = None,
        formatter: ProductFormatter | None = None,
        quality_checker: QualityChecker | None = None,
        updater: ProductUpdater | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        if translator is None:
            raise TypeError(
                "translator ir obligāta DescriptionPipeline atkarība."
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

        self.config = (
            config
            if config is not None
            else PipelineConfig()
        )

    def process(
        self,
        product: ProductDescription,
    ) -> PipelineResult:
        """Process one parsed product through the complete pipeline.

        Processing order:

        1. Build deterministic translation context.
        2. Generate and validate the translation draft.
        3. Format the draft for WooCommerce.
        4. Run deterministic quality checks.
        5. Apply or plan the WooCommerce update.

        Exceptions raised by individual components are intentionally not
        caught or replaced. The caller therefore receives the original
        error type and traceback from the component that failed.

        Args:
            product:
                Parsed supplier product description.

        Returns:
            PipelineResult containing all intermediate and final objects.

        Raises:
            PipelineQualityError:
                If quality checking fails and
                fail_on_quality_errors is enabled.

            TypeError:
                If an invalid product object is supplied.

            Exception:
                Any exception raised by the configured pipeline
                components is propagated unchanged.
        """

        if not isinstance(product, ProductDescription):
            raise TypeError(
                "product jābūt ProductDescription objektam."
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

        if (
            self.config.fail_on_quality_errors
            and not quality.passed
        ):
            raise PipelineQualityError(
                (
                    f"Produkta {formatted.sku} apraksts "
                    "neizturēja kvalitātes pārbaudi."
                ),
                quality_report=quality,
            )

        update = self.updater.update(
            product=formatted,
            quality_report=quality,
        )

        return PipelineResult(
            context=context,
            draft=draft,
            formatted=formatted,
            quality=quality,
            update=update,
        )