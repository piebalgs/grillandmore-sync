from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.descriptions.llm_client import (
    FakeLLMClient,
    LLMClient,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
)
from src.descriptions.models import PromptPackage


def make_prompt(**overrides) -> PromptPackage:
    values = {
        "system_prompt": "System",
        "user_prompt": "User",
        "response_schema": {"type": "object"},
        "metadata": {"sku": "ABC-123"},
    }
    values.update(overrides)
    return PromptPackage(**values)


def test_response_stores_provider_neutral_fields():
    response = LLMResponse(
        content='{"title":"Test"}',
        model="fake-model",
        request_id="req-1",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        metadata={"provider": "fake"},
    )
    assert response.content == '{"title":"Test"}'
    assert response.model == "fake-model"
    assert response.request_id == "req-1"
    assert response.metadata["provider"] == "fake"


def test_response_calculates_token_properties():
    response = LLMResponse(
        content="ok",
        usage={"prompt_tokens": 7, "completion_tokens": 3},
    )
    assert response.prompt_tokens == 7
    assert response.completion_tokens == 3
    assert response.total_tokens == 10


def test_explicit_total_tokens_has_priority():
    response = LLMResponse(
        content="ok",
        usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 12},
    )
    assert response.total_tokens == 12


def test_missing_usage_values_default_to_zero():
    response = LLMResponse(content="ok")
    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0
    assert response.total_tokens == 0


def test_response_is_frozen():
    response = LLMResponse(content="ok")
    with pytest.raises(FrozenInstanceError):
        response.content = "changed"


def test_usage_is_copied_and_immutable():
    usage = {"prompt_tokens": 4}
    response = LLMResponse(content="ok", usage=usage)
    usage["prompt_tokens"] = 99
    assert response.prompt_tokens == 4
    with pytest.raises(TypeError):
        response.usage["prompt_tokens"] = 5


def test_metadata_is_copied_and_immutable():
    metadata = {"provider": "fake"}
    response = LLMResponse(content="ok", metadata=metadata)
    metadata["provider"] = "changed"
    assert response.metadata["provider"] == "fake"
    with pytest.raises(TypeError):
        response.metadata["provider"] = "changed"


@pytest.mark.parametrize("value", [1, None, [], {}])
def test_content_must_be_text(value):
    with pytest.raises(TypeError, match="content"):
        LLMResponse(content=value)


@pytest.mark.parametrize("usage", [{"prompt_tokens": 1.5}, {"prompt_tokens": True}])
def test_usage_values_must_be_integers(usage):
    with pytest.raises(TypeError, match="veseliem skaitļiem"):
        LLMResponse(content="ok", usage=usage)


def test_usage_values_cannot_be_negative():
    with pytest.raises(ValueError, match="negatīvas"):
        LLMResponse(content="ok", usage={"prompt_tokens": -1})


def test_fake_client_implements_protocol():
    assert isinstance(FakeLLMClient(), LLMClient)


def test_fake_client_returns_queued_string_as_response():
    client = FakeLLMClient(["first"])
    response = client.generate(make_prompt())
    assert response == LLMResponse(content="first", model="fake")


def test_fake_client_returns_existing_response_unchanged():
    expected = LLMResponse(content="first", model="model-x")
    client = FakeLLMClient([expected])
    assert client.generate(make_prompt()) is expected


def test_fake_client_consumes_responses_fifo():
    client = FakeLLMClient(["first", "second"])
    assert client.generate(make_prompt()).content == "first"
    assert client.generate(make_prompt()).content == "second"
    assert client.remaining_response_count == 0


def test_fake_client_captures_prompt_and_call_count():
    prompt = make_prompt()
    client = FakeLLMClient(["ok"])
    client.generate(prompt)
    assert client.call_count == 1
    assert client.calls[0].prompt is prompt
    assert client.prompts == (prompt,)


def test_fake_client_raises_queued_exception():
    client = FakeLLMClient([LLMRequestError("provider failed")])
    with pytest.raises(LLMRequestError, match="provider failed"):
        client.generate(make_prompt())
    assert client.call_count == 1


def test_fake_client_uses_default_response_repeatedly():
    client = FakeLLMClient(default_response="fallback")
    assert client.generate(make_prompt()).content == "fallback"
    assert client.generate(make_prompt()).content == "fallback"
    assert client.call_count == 2


def test_fake_client_without_response_fails_explicitly():
    client = FakeLLMClient()
    with pytest.raises(LLMResponseError, match="nav sagatavota"):
        client.generate(make_prompt())


def test_fake_client_queue_appends_items():
    client = FakeLLMClient()
    client.queue("one", "two")
    assert client.remaining_response_count == 2
    assert client.generate(make_prompt()).content == "one"


def test_reset_calls_does_not_remove_responses():
    client = FakeLLMClient(["one", "two"])
    client.generate(make_prompt())
    client.reset_calls()
    assert client.call_count == 0
    assert client.remaining_response_count == 1
    assert client.generate(make_prompt()).content == "two"


def test_fake_client_rejects_non_prompt_package():
    client = FakeLLMClient(["ok"])
    with pytest.raises(TypeError, match="PromptPackage"):
        client.generate("not a prompt")
    assert client.call_count == 0


def test_fake_client_rejects_invalid_queued_item():
    with pytest.raises(TypeError, match="LLMResponse vai tekstam"):
        FakeLLMClient([123])
