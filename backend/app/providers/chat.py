"""Chat model adapters with one interface: `stream()` for answers, `complete()` for short calls.

Each adapter talks to its provider's official SDK. `request()` builds the request
parameters as a plain dict so the per-model rules are easy to unit test.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import openai
from google import genai

from app.providers.catalog import ANTHROPIC, GOOGLE, MOCK, OPENAI, PROVIDER_LABELS, ChatModel, chat_model
from app.providers.errors import ProviderError, translate
from app.providers.keys import ApiKeys

REFUSAL_NOTE = "\n\n_The model declined to answer this request._"
TRUNCATED_NOTE = "\n\n_The answer was cut off at the output limit._"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


class ChatClient(Protocol):
    model: ChatModel

    def stream(
        self, system: str, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]: ...

    async def complete(self, system: str, messages: list[Message]) -> str: ...


class OpenAIChat:
    """OpenAI Responses API."""

    MAX_OUTPUT_TOKENS = 8192  # reasoning tokens count toward this limit

    def __init__(self, model: ChatModel, api_key: str, client: openai.AsyncOpenAI | None = None):
        self.model = model
        self.client = client or openai.AsyncOpenAI(api_key=api_key)

    def request(self, system: str, messages: list[Message], temperature: float | None) -> dict:
        params: dict = {
            "model": self.model.id,
            "instructions": system,
            "input": [{"role": m.role, "content": m.content} for m in messages],
            "max_output_tokens": self.MAX_OUTPUT_TOKENS,
            "store": False,
        }
        if self.model.reasoning:
            params["reasoning"] = {"effort": "low"}
        if self.model.temperature and temperature is not None:
            params["temperature"] = temperature
        return params

    async def stream(
        self, system: str, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        try:
            events = await self.client.responses.create(
                stream=True, **self.request(system, messages, temperature)
            )
            async for event in events:
                if event.type == "response.output_text.delta":
                    yield event.delta
                elif event.type == "response.incomplete":
                    yield TRUNCATED_NOTE
                elif event.type == "response.failed":
                    error = event.response.error
                    raise ProviderError(f"OpenAI failed: {error.message if error else 'unknown error'}")
                elif event.type == "error":
                    raise ProviderError(f"OpenAI failed: {event.message}")
        except Exception as exc:
            raise translate(exc, "OpenAI") from exc

    async def complete(self, system: str, messages: list[Message]) -> str:
        try:
            response = await self.client.responses.create(**self.request(system, messages, 0.0))
        except Exception as exc:
            raise translate(exc, "OpenAI") from exc
        return response.output_text


class AnthropicChat:
    """Anthropic Messages API.

    Claude 5.5 models always think; `output_config.effort` sets how much, and `low`
    suits short grounded answers. They reject sampling parameters, so temperature is
    never sent. They also run safety classifiers that can decline a request, so
    `fallbacks: "default"` lets the API retry a declined request on a suitable model.
    """

    STREAM_MAX_TOKENS = 64000
    COMPLETE_MAX_TOKENS = 8000
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: ChatModel, api_key: str, client: anthropic.AsyncAnthropic | None = None):
        self.model = model
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key)

    def request(self, system: str, messages: list[Message], max_tokens: int) -> dict:
        params: dict = {
            "model": self.model.id,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self.model.effort:
            params["output_config"] = {"effort": "low"}
        if self.model.fallbacks:
            params["betas"] = [self.FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def _api(self, params: dict):
        return self.client.beta.messages if "betas" in params else self.client.messages

    async def stream(
        self, system: str, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        params = self.request(system, messages, self.STREAM_MAX_TOKENS)
        try:
            async with self._api(params).stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        except Exception as exc:
            raise translate(exc, "Anthropic") from exc
        if final.stop_reason == "refusal":
            yield REFUSAL_NOTE
        elif final.stop_reason == "max_tokens":
            yield TRUNCATED_NOTE

    async def complete(self, system: str, messages: list[Message]) -> str:
        params = self.request(system, messages, self.COMPLETE_MAX_TOKENS)
        try:
            response = await self._api(params).create(**params)
        except Exception as exc:
            raise translate(exc, "Anthropic") from exc
        if response.stop_reason == "refusal":
            return ""
        return "".join(block.text for block in response.content if block.type == "text")


class GoogleChat:
    """Gemini via the google-genai SDK."""

    MAX_OUTPUT_TOKENS = 8192  # thinking tokens count toward this limit

    def __init__(self, model: ChatModel, api_key: str, client: genai.Client | None = None):
        self.model = model
        self.client = client or genai.Client(api_key=api_key)

    def request(self, system: str, messages: list[Message], temperature: float | None) -> dict:
        config: dict = {
            "system_instruction": system,
            "max_output_tokens": self.MAX_OUTPUT_TOKENS,
            "automatic_function_calling": {"disable": True},  # no tools are passed
        }
        if self.model.temperature and temperature is not None:
            config["temperature"] = temperature
        contents = [
            {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
            for m in messages
        ]
        return {"model": self.model.id, "contents": contents, "config": config}

    async def stream(
        self, system: str, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        try:
            chunks = await self.client.aio.models.generate_content_stream(
                **self.request(system, messages, temperature)
            )
            async for chunk in chunks:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise translate(exc, "Google Gemini") from exc

    async def complete(self, system: str, messages: list[Message]) -> str:
        try:
            response = await self.client.aio.models.generate_content(**self.request(system, messages, 0.0))
        except Exception as exc:
            raise translate(exc, "Google Gemini") from exc
        return response.text or ""


def chat_client(provider: str, model_id: str, keys: ApiKeys, *, mock_enabled: bool) -> ChatClient:
    if provider == MOCK:
        if not mock_enabled:
            raise ProviderError("The mock provider is disabled on this server.", 400)
        from app.providers.mock import MockChat

        return MockChat(chat_model(MOCK, model_id))

    if provider not in (OPENAI, ANTHROPIC, GOOGLE):
        raise ProviderError(f"Unknown provider '{provider}'.", 400)
    if not model_id.strip():
        raise ProviderError(f"Pick a {PROVIDER_LABELS[provider]} model.", 400)

    model = chat_model(provider, model_id.strip())
    api_key = keys.for_provider(provider)
    if provider == OPENAI:
        return OpenAIChat(model, api_key)
    if provider == ANTHROPIC:
        return AnthropicChat(model, api_key)
    return GoogleChat(model, api_key)
