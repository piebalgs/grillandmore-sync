"""Tests for centralized project configuration."""

from __future__ import annotations

import pytest

from src.core.config import (
    ConfigurationError,
    create_settings,
)


@pytest.fixture
def clean_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove configuration values relevant to these tests."""

    names = (
        "WC_URL",
        "WC_CONSUMER_KEY",
        "WC_CONSUMER_SECRET",
        "WP_USERNAME",
        "WP_APP_PASSWORD",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT",
    )

    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_openai_settings_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: None,
) -> None:
    """OpenAI configuration is loaded into Settings."""

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "  test-openai-key  ",
    )
    monkeypatch.setenv(
        "OPENAI_MODEL",
        "  test-model  ",
    )
    monkeypatch.setenv(
        "OPENAI_TIMEOUT",
        "45",
    )

    settings = create_settings()

    assert settings.openai_api_key == "test-openai-key"
    assert settings.openai_model == "test-model"
    assert settings.openai_timeout == 45


def test_openai_timeout_has_default(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: None,
) -> None:
    """OpenAI timeout has a safe default."""

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-openai-key",
    )
    monkeypatch.setenv(
        "OPENAI_MODEL",
        "test-model",
    )

    settings = create_settings()

    assert settings.openai_timeout == 60


def test_validate_openai_reports_missing_values(
    clean_environment: None,
) -> None:
    """Missing required OpenAI values are reported together."""

    settings = create_settings()

    assert settings.missing_openai_values() == (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    )

    with pytest.raises(
        ConfigurationError,
        match="OPENAI_API_KEY, OPENAI_MODEL",
    ):
        settings.validate_openai()


def test_validate_openai_accepts_complete_configuration(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: None,
) -> None:
    """Complete OpenAI configuration passes validation."""

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-openai-key",
    )
    monkeypatch.setenv(
        "OPENAI_MODEL",
        "test-model",
    )

    settings = create_settings()

    assert settings.missing_openai_values() == ()
    settings.validate_openai()


def test_openai_timeout_rejects_zero(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: None,
) -> None:
    """OpenAI timeout must be greater than zero."""

    monkeypatch.setenv(
        "OPENAI_TIMEOUT",
        "0",
    )

    with pytest.raises(
        ConfigurationError,
        match="OPENAI_TIMEOUT jābūt vismaz 1",
    ):
        create_settings()


def test_openai_timeout_rejects_non_integer(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: None,
) -> None:
    """OpenAI timeout must be an integer."""

    monkeypatch.setenv(
        "OPENAI_TIMEOUT",
        "abc",
    )

    with pytest.raises(
        ConfigurationError,
        match="OPENAI_TIMEOUT jābūt veselam skaitlim",
    ):
        create_settings()