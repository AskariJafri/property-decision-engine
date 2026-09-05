"""What the provider actually puts on the wire.

The runtime tests substitute the provider wholesale, so nothing else checks that
this speaks the OpenAI-compatible shape it promises — which is the whole basis
for the claim that a local Ollama and a hosted tier differ by a URL and a name.
"""

import json

import httpx
import pytest

from app.ai.contracts import LlmUnavailableError
from app.ai.provider import OpenAICompatibleProvider
from app.core.config import Settings

SCHEMA: dict[str, object] = {"type": "object"}


def reply(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


class TestRequestShape:
    async def test_a_hosted_tier_gets_a_bearer_token(self):
        """Ollama needs no Authorization header; every hosted tier requires one."""
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return reply({"ok": True})

        settings = Settings(llm_api_key="secret-token", llm_base_url="https://api.example.com/v1")
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with client:
            await OpenAICompatibleProvider(settings, client).complete_json(
                system="s", user="u", schema=SCHEMA
            )

        assert seen["auth"] == "Bearer secret-token"
        assert seen["url"] == "https://api.example.com/v1/chat/completions"

    async def test_a_local_model_gets_no_authorization_header(self):
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return reply({"ok": True})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with client:
            await OpenAICompatibleProvider(Settings(llm_api_key=""), client).complete_json(
                system="s", user="u", schema=SCHEMA
            )

        assert seen["auth"] is None

    async def test_sampling_is_pinned_and_the_exact_tag_is_sent(self):
        """Temperature 0 and a fixed seed are what make a judgement replayable,
        and an alias like "llama3" would be pinned to nothing."""
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return reply({"ok": True})

        settings = Settings(llm_model="llama3.1:8b-instruct-q4_K_M", llm_seed=7)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with client:
            await OpenAICompatibleProvider(settings, client).complete_json(
                system="s", user="u", schema=SCHEMA
            )

        assert seen["temperature"] == 0.0
        assert seen["seed"] == 7
        assert seen["model"] == "llama3.1:8b-instruct-q4_K_M"


class TestFailures:
    async def test_an_unreachable_model_is_unavailable_not_an_error(self):
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
        async with client:
            with pytest.raises(LlmUnavailableError, match="could not be reached"):
                await OpenAICompatibleProvider(Settings(), client).complete_json(
                    system="s", user="u", schema=SCHEMA
                )

    async def test_non_json_output_is_discarded_rather_than_repaired(self):
        def prose(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "Sure! Here you go:"}}]}
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(prose))
        async with client:
            with pytest.raises(LlmUnavailableError, match="not return valid JSON"):
                await OpenAICompatibleProvider(Settings(), client).complete_json(
                    system="s", user="u", schema=SCHEMA
                )

    async def test_an_empty_base_url_means_no_model_configured(self):
        settings = Settings()
        settings.llm_base_url = ""
        with pytest.raises(LlmUnavailableError, match="No model is configured"):
            await OpenAICompatibleProvider(settings).complete_json(
                system="s", user="u", schema=SCHEMA
            )

    async def test_blanking_the_base_url_does_not_turn_the_model_off(self):
        """A trap worth pinning down, because the obvious way to disable a model
        is to blank its URL — and here that does the opposite.

        ``blank_means_unset`` treats an empty environment variable as absent so
        the default applies, which is right for the crash it was written for and
        surprising here: ``PDE_LLM_BASE_URL=""`` restores the localhost default
        rather than clearing it. ``PDE_LLM_EXPLANATIONS_ENABLED`` is the switch;
        blanking the URL is not one.
        """
        assert Settings(llm_base_url="").llm_base_url == "http://localhost:11434/v1"
