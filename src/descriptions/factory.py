"""Factories for fully configured description processing components."""

from __future__ import annotations

from src.core.config import Settings
from src.descriptions.grill_description_orchestrator import (
    GrillDescriptionOrchestrator,
)
from src.descriptions.openai_llm_client import OpenAILLMClient
from src.descriptions.translator import Translator
from src.descriptions.updater import (
    ProductUpdater,
    ProductUpdaterConfig,
)


def create_grill_description_orchestrator(
    *,
    settings: Settings,
) -> GrillDescriptionOrchestrator:
    """
    Build a safe Weber grill description orchestrator.

    OpenAI configuration is taken from the centralized Settings object.

    WooCommerce updates are deliberately configured as DRY RUN and
    existing WooCommerce product titles are preserved.
    """

    if not isinstance(settings, Settings):
        raise TypeError(
            "settings jābūt Settings objektam."
        )

    settings.validate_openai()

    llm_client = OpenAILLMClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=settings.openai_timeout,
    )

    translator = Translator(
        llm_client=llm_client,
    )

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        )
    )

    return GrillDescriptionOrchestrator(
        translator=translator,
        updater=updater,
    )