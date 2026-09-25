"""OpenAI adapter for the provider-neutral LLM client contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from src.descriptions.llm_client import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
)
from src.descriptions.models import PromptPackage


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAILLMClient:
    """OpenAI implementation of the provider-neutral LLM client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        normalized_api_key = api_key.strip()
        normalized_model = model.strip()

        if not normalized_api_key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY nav norādīts."
            )

        if not normalized_model:
            raise LLMConfigurationError(
                "OpenAI model nosaukums nav norādīts."
            )

        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise LLMConfigurationError(
                "OpenAI timeout jābūt veselam skaitlim."
            )

        if timeout <= 0:
            raise LLMConfigurationError(
                "OpenAI timeout jābūt lielākam par 0."
            )

        self.api_key = normalized_api_key
        self.model = normalized_model
        self.timeout = timeout

    def generate(self, prompt: PromptPackage) -> LLMResponse:
        """Generate one structured response through OpenAI Responses API."""

        if not isinstance(prompt, PromptPackage):
            raise TypeError(
                "OpenAILLMClient.generate sagaida PromptPackage."
            )

        try:
            response = requests.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": prompt.system_prompt,
                    "input": prompt.user_prompt,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "translation_response",
                            "strict": True,
                            "schema": dict(prompt.response_schema),
                        },
                    },
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMRequestError(
                "OpenAI API pieprasījums neizdevās."
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise LLMResponseError(
                (
                    "OpenAI API atgrieza HTTP "
                    f"{response.status_code}."
                )
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "OpenAI API neatgrieza derīgu JSON atbildi."
            ) from exc

        if not isinstance(payload, Mapping):
            raise LLMResponseError(
                "OpenAI API atbildes saknei jābūt JSON objektam."
            )

        content = self._extract_output_text(payload)
        usage = self._extract_usage(payload)

        request_id = str(
            response.headers.get("x-request-id") or ""
        )

        model = str(
            payload.get("model") or self.model
        )

        return LLMResponse(
            content=content,
            model=model,
            request_id=request_id,
            usage=usage,
            metadata={
                "response_id": str(payload.get("id") or ""),
            },
        )

    @staticmethod
    def _extract_output_text(
        payload: Mapping[str, Any],
    ) -> str:
        """Extract the first output_text value from a Responses payload."""

        output = payload.get("output")

        if not isinstance(output, list):
            raise LLMResponseError(
                "OpenAI API atbildē trūkst output saraksta."
            )

        for item in output:
            if not isinstance(item, Mapping):
                continue

            content = item.get("content")

            if not isinstance(content, list):
                continue

            for part in content:
                if not isinstance(part, Mapping):
                    continue

                if part.get("type") != "output_text":
                    continue

                text = part.get("text")

                if isinstance(text, str) and text.strip():
                    return text

        raise LLMResponseError(
            "OpenAI API atbildē nav atrasts output_text."
        )

    @staticmethod
    def _extract_usage(
        payload: Mapping[str, Any],
    ) -> dict[str, int]:
        """Convert OpenAI token usage to the provider-neutral contract."""

        raw_usage = payload.get("usage")

        if not isinstance(raw_usage, Mapping):
            return {}

        input_tokens = raw_usage.get("input_tokens", 0)
        output_tokens = raw_usage.get("output_tokens", 0)
        total_tokens = raw_usage.get("total_tokens", 0)

        return {
            "prompt_tokens": (
                input_tokens
                if isinstance(input_tokens, int)
                and not isinstance(input_tokens, bool)
                and input_tokens >= 0
                else 0
            ),
            "completion_tokens": (
                output_tokens
                if isinstance(output_tokens, int)
                and not isinstance(output_tokens, bool)
                and output_tokens >= 0
                else 0
            ),
            "total_tokens": (
                total_tokens
                if isinstance(total_tokens, int)
                and not isinstance(total_tokens, bool)
                and total_tokens >= 0
                else 0
            ),
        }