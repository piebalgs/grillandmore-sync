"""Provider-neutral language-model client contracts and deterministic test doubles."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from src.descriptions.models import PromptPackage


class LLMClientError(RuntimeError):
    """Base error raised when an LLM client cannot complete a request."""


class LLMConfigurationError(LLMClientError):
    """Raised when an LLM client is configured with invalid settings."""


class LLMRequestError(LLMClientError):
    """Raised when a provider rejects or cannot process a request."""


class LLMResponseError(LLMClientError):
    """Raised when a provider returns an unusable response."""


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a shallow immutable copy of a mapping."""
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Provider-neutral text response and technical request metadata."""

    content: str
    model: str = ""
    request_id: str = ""
    usage: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("LLMResponse.content jābūt tekstam.")
        if not isinstance(self.model, str):
            raise TypeError("LLMResponse.model jābūt tekstam.")
        if not isinstance(self.request_id, str):
            raise TypeError("LLMResponse.request_id jābūt tekstam.")

        normalized_usage: dict[str, int] = {}
        for key, value in self.usage.items():
            if not isinstance(key, str):
                raise TypeError("LLMResponse.usage atslēgām jābūt tekstam.")
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("LLMResponse.usage vērtībām jābūt veseliem skaitļiem.")
            if value < 0:
                raise ValueError("LLMResponse.usage vērtības nedrīkst būt negatīvas.")
            normalized_usage[key] = value

        object.__setattr__(self, "usage", _freeze_mapping(normalized_usage))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)

    @property
    def total_tokens(self) -> int:
        explicit_total = self.usage.get("total_tokens")
        if explicit_total is not None:
            return explicit_total
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMClient(Protocol):
    """Minimal contract implemented by every language-model provider client."""

    def generate(self, prompt: PromptPackage) -> LLMResponse:
        """Generate one response for a complete provider-neutral prompt package."""
        ...


@dataclass(frozen=True, slots=True)
class LLMCall:
    """One prompt captured by FakeLLMClient for deterministic assertions."""

    prompt: PromptPackage


class FakeLLMClient:
    """Deterministic in-memory client for unit tests and local development.

    Responses and exceptions are consumed in FIFO order. A plain string is
    converted to ``LLMResponse(content=...)`` automatically.
    """

    def __init__(
        self,
        responses: Iterable[LLMResponse | str | BaseException] = (),
        *,
        default_response: LLMResponse | str | None = None,
    ) -> None:
        self._responses: deque[LLMResponse | BaseException] = deque(
            self._coerce_item(item) for item in responses
        )
        self._default_response = (
            self._coerce_response(default_response)
            if default_response is not None
            else None
        )
        self._calls: list[LLMCall] = []

    @staticmethod
    def _coerce_response(value: LLMResponse | str) -> LLMResponse:
        if isinstance(value, LLMResponse):
            return value
        if isinstance(value, str):
            return LLMResponse(content=value, model="fake")
        raise TypeError("FakeLLMClient atbildei jābūt LLMResponse vai tekstam.")

    @classmethod
    def _coerce_item(
        cls,
        value: LLMResponse | str | BaseException,
    ) -> LLMResponse | BaseException:
        if isinstance(value, BaseException):
            return value
        return cls._coerce_response(value)

    @property
    def calls(self) -> tuple[LLMCall, ...]:
        """Return an immutable snapshot of captured calls."""
        return tuple(self._calls)

    @property
    def prompts(self) -> tuple[PromptPackage, ...]:
        """Return only captured prompt packages."""
        return tuple(call.prompt for call in self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def remaining_response_count(self) -> int:
        return len(self._responses)

    def queue(self, *items: LLMResponse | str | BaseException) -> None:
        """Append responses or exceptions to the deterministic FIFO queue."""
        self._responses.extend(self._coerce_item(item) for item in items)

    def reset_calls(self) -> None:
        """Clear captured calls without changing queued responses."""
        self._calls.clear()

    def generate(self, prompt: PromptPackage) -> LLMResponse:
        if not isinstance(prompt, PromptPackage):
            raise TypeError("FakeLLMClient.generate sagaida PromptPackage.")

        self._calls.append(LLMCall(prompt=prompt))

        if self._responses:
            item = self._responses.popleft()
        elif self._default_response is not None:
            item = self._default_response
        else:
            raise LLMResponseError(
                "FakeLLMClient nav sagatavota neviena atbilde."
            )

        if isinstance(item, BaseException):
            raise item
        return item
