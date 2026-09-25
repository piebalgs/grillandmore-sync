"""Tests for the OpenAI LLM client adapter."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from src.descriptions.llm_client import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from src.descriptions.models import PromptPackage
from src.descriptions.openai_llm_client import (
    OpenAILLMClient,
)


def _make_prompt() -> PromptPackage:
    """Return a minimal valid prompt for adapter tests."""

    return PromptPackage(
        system_prompt="System instructions",
        user_prompt="Translate this product.",
        response_schema={
            "type": "object",
        },
        metadata={
            "sku": "1501071",
        },
    )


def test_openai_client_requires_api_key() -> None:
    """API key is mandatory."""

    with pytest.raises(
        LLMConfigurationError,
        match="OPENAI_API_KEY",
    ):
        OpenAILLMClient(
            api_key="",
            model="test-model",
        )


def test_openai_client_requires_model() -> None:
    """Model name is mandatory."""

    with pytest.raises(
        LLMConfigurationError,
        match="model",
    ):
        OpenAILLMClient(
            api_key="test-key",
            model="",
        )


def test_openai_client_normalizes_configuration() -> None:
    """Configuration values are normalized once at construction."""

    client = OpenAILLMClient(
        api_key="  test-key  ",
        model="  test-model  ",
        timeout=45,
    )

    assert client.api_key == "test-key"
    assert client.model == "test-model"
    assert client.timeout == 45


def test_generate_sends_prompt_and_returns_llm_response() -> None:
    """A successful OpenAI response is converted to LLMResponse."""

    client = OpenAILLMClient(
        api_key="test-key",
        model="test-model",
        timeout=45,
    )

    response = Mock()
    response.status_code = 200
    response.headers = {
        "x-request-id": "req-test-123",
    }
    response.json.return_value = {
        "id": "resp-test-123",
        "model": "test-model",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"title":"Latviešu nosaukums"}',
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 25,
            "total_tokens": 125,
        },
    }

    with patch(
        "src.descriptions.openai_llm_client.requests.post",
        return_value=response,
    ) as post:
        result = client.generate(_make_prompt())

    post.assert_called_once()

    _, kwargs = post.call_args

    assert kwargs["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert kwargs["timeout"] == 45

    payload = kwargs["json"]

    assert payload["model"] == "test-model"
    assert payload["instructions"] == "System instructions"
    assert payload["input"] == "Translate this product."

    assert payload["text"]["format"] == {
        "type": "json_schema",
        "name": "translation_response",
        "strict": True,
        "schema": {
            "type": "object",
        },
    }

    assert result.content == '{"title":"Latviešu nosaukums"}'
    assert result.model == "test-model"
    assert result.request_id == "req-test-123"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 25
    assert result.total_tokens == 125


def test_generate_rejects_http_error() -> None:
    """Non-success HTTP responses are rejected."""

    client = OpenAILLMClient(
        api_key="test-key",
        model="test-model",
    )

    response = Mock()
    response.status_code = 429
    response.headers = {}
    response.json.return_value = {
        "error": {
            "message": "Rate limit exceeded",
        }
    }

    with patch(
        "src.descriptions.openai_llm_client.requests.post",
        return_value=response,
    ):
        with pytest.raises(
            LLMResponseError,
            match="HTTP 429",
        ):
            client.generate(_make_prompt())


def test_generate_rejects_invalid_json_response() -> None:
    """Invalid JSON returned by OpenAI is rejected."""

    client = OpenAILLMClient(
        api_key="test-key",
        model="test-model",
    )

    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.json.side_effect = ValueError("invalid json")

    with patch(
        "src.descriptions.openai_llm_client.requests.post",
        return_value=response,
    ):
        with pytest.raises(
            LLMResponseError,
            match="derīgu JSON",
        ):
            client.generate(_make_prompt())


def test_generate_rejects_missing_output_text() -> None:
    """A successful response must contain output_text."""

    client = OpenAILLMClient(
        api_key="test-key",
        model="test-model",
    )

    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {
        "id": "resp-test-empty",
        "model": "test-model",
        "output": [],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 0,
            "total_tokens": 10,
        },
    }

    with patch(
        "src.descriptions.openai_llm_client.requests.post",
        return_value=response,
    ):
        with pytest.raises(
            LLMResponseError,
            match="output_text",
        ):
            client.generate(_make_prompt())


def test_generate_converts_request_error() -> None:
    """Network failures are converted to the LLM client contract."""

    client = OpenAILLMClient(
        api_key="test-key",
        model="test-model",
    )

    with patch(
        "src.descriptions.openai_llm_client.requests.post",
        side_effect=requests.Timeout("request timed out"),
    ):
        with pytest.raises(
            LLMRequestError,
            match="OpenAI API pieprasījums neizdevās",
        ):
            client.generate(_make_prompt())