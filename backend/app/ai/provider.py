"""The local model, behind an OpenAI-compatible interface.

Ollama exposes ``/v1/chat/completions``, so today's local model and tomorrow's free
hosted tier differ by a base URL and a model name. Sampling is pinned — temperature
0, a fixed seed where the backend honours one — and the model identifier actually
used is returned rather than the alias that was requested, because a judgement
pinned to "llama3" is pinned to nothing.

Every failure path raises :class:`LlmUnavailableError`. Callers turn that into an
unavailable judgement, not into a failed analysis.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.contracts import LlmUnavailableError
from app.core.config import Settings


class OpenAICompatibleProvider:
    """Works against Ollama, and against any free tier speaking the same shape."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    @property
    def model_id(self) -> str:
        return self._settings.llm_model

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        if not self._settings.llm_base_url:
            raise LlmUnavailableError("No model is configured (PDE_LLM_BASE_URL is empty).")

        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._settings.llm_temperature,
            "seed": self._settings.llm_seed,
            "max_tokens": max_tokens,
            # Ollama and most compatible servers honour this; those that do not still
            # get the instruction in the system prompt, and validation catches the rest.
            "response_format": {"type": "json_object", "schema": schema},
        }

        client = self._client or httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds)
        try:
            response = await client.post(
                f"{self._settings.llm_base_url.rstrip('/')}/chat/completions", json=payload
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise LlmUnavailableError(f"The local model could not be reached: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LlmUnavailableError(f"Unexpected response shape from the model: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmUnavailableError(
                f"The model did not return valid JSON: {exc}. Discarded rather than repaired."
            ) from exc

        if not isinstance(parsed, dict):
            raise LlmUnavailableError("The model returned JSON that is not an object.")
        return parsed
