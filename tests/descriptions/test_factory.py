"""Tests for description component factories."""

from __future__ import annotations

from src.core.config import Settings
from src.descriptions.factory import (
    create_grill_description_orchestrator,
)
from src.descriptions.openai_llm_client import OpenAILLMClient


def _make_settings() -> Settings:
    """Return isolated settings for factory tests."""

    from pathlib import Path

    return Settings(
        project_root=Path("/test"),
        env_file=Path("/test/.env"),
        wc_url="https://example.com/shop",
        wc_consumer_key="consumer-key",
        wc_consumer_secret="consumer-secret",
        wp_username="wordpress-user",
        wp_app_password="wordpress-password",
        openai_api_key="test-openai-key",
        openai_model="test-openai-model",
        openai_timeout=45,
        retry_status_codes=frozenset(
            {
                429,
                500,
                502,
                503,
                504,
            }
        ),
        retry_delays=(20, 45, 90),
        product_update_pause=3,
        max_images_per_product=10,
    )


def test_factory_builds_openai_translator() -> None:
    """Factory connects Settings to OpenAI and Translator."""

    settings = _make_settings()

    orchestrator = create_grill_description_orchestrator(
        settings=settings,
    )

    llm_client = orchestrator.translator.llm_client

    assert isinstance(
        llm_client,
        OpenAILLMClient,
    )

    assert llm_client.api_key == "test-openai-key"
    assert llm_client.model == "test-openai-model"
    assert llm_client.timeout == 45


def test_factory_builds_safe_dry_run_updater() -> None:
    """Factory must never enable live Woo writes by default."""

    settings = _make_settings()

    orchestrator = create_grill_description_orchestrator(
        settings=settings,
    )

    assert orchestrator.updater.config.dry_run is True
    assert orchestrator.updater.config.update_title is False


def test_factory_validates_openai_configuration() -> None:
    """Factory rejects incomplete OpenAI configuration."""

    settings = _make_settings()

    invalid_settings = Settings(
        project_root=settings.project_root,
        env_file=settings.env_file,
        wc_url=settings.wc_url,
        wc_consumer_key=settings.wc_consumer_key,
        wc_consumer_secret=settings.wc_consumer_secret,
        wp_username=settings.wp_username,
        wp_app_password=settings.wp_app_password,
        openai_api_key="",
        openai_model=settings.openai_model,
        openai_timeout=settings.openai_timeout,
        retry_status_codes=settings.retry_status_codes,
        retry_delays=settings.retry_delays,
        product_update_pause=settings.product_update_pause,
        max_images_per_product=settings.max_images_per_product,
    )

    from src.core.config import ConfigurationError

    try:
        create_grill_description_orchestrator(
            settings=invalid_settings,
        )
    except ConfigurationError as error:
        assert "OPENAI_API_KEY" in str(error)
    else:
        raise AssertionError(
            "Factory bija jāatsaka tukšs OPENAI_API_KEY."
        )