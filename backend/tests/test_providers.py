import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.config import Settings
from app.providers.catalog import ANTHROPIC, GOOGLE, OPENAI, chat_model
from app.providers.chat import REFUSAL_NOTE, AnthropicChat, GoogleChat, Message, OpenAIChat
from app.providers.errors import ProviderError
from app.providers.keys import ApiKeys, resolve_keys

HISTORY = [Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "What is RAG?")]


def collect(stream) -> list[str]:
    async def run():
        return [piece async for piece in stream]

    return asyncio.run(run())


# Request parameters per model family


def test_openai_reasoning_models_get_effort_and_no_temperature():
    params = OpenAIChat(chat_model(OPENAI, "gpt-5.4-mini"), "k").request("sys", HISTORY, 0.7)
    assert params["reasoning"] == {"effort": "low"}
    assert "temperature" not in params
    assert params["instructions"] == "sys"
    assert params["input"][-1] == {"role": "user", "content": "What is RAG?"}
    assert params["store"] is False


def test_openai_classic_models_take_temperature():
    params = OpenAIChat(chat_model(OPENAI, "gpt-4o-mini"), "k").request("sys", HISTORY, 0.7)
    assert params["temperature"] == 0.7
    assert "reasoning" not in params


def test_custom_openai_model_ids_are_classified_by_family():
    assert chat_model(OPENAI, "gpt-5.9-pro").reasoning
    assert not chat_model(OPENAI, "gpt-4.1").reasoning
    assert chat_model(OPENAI, "gpt-4.1").temperature


def test_claude_5_5_gets_effort_and_fallbacks_but_never_temperature():
    params = AnthropicChat(chat_model(ANTHROPIC, "claude-opus-5-5"), "k").request("sys", HISTORY, 64000)
    assert params["output_config"] == {"effort": "low"}
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["fallbacks"] == "default"
    assert "temperature" not in params
    assert params["system"] == "sys"


def test_claude_haiku_and_custom_claude_ids_send_no_optional_parameters():
    for model_id in ("claude-haiku-4-5", "claude-some-future-model"):
        params = AnthropicChat(chat_model(ANTHROPIC, model_id), "k").request("sys", HISTORY, 1000)
        assert set(params) == {"model", "max_tokens", "system", "messages"}


def test_gemini_maps_roles_and_takes_temperature():
    params = GoogleChat(chat_model(GOOGLE, "gemini-2.5-flash"), "k").request("sys", HISTORY, 0.2)
    assert [c["role"] for c in params["contents"]] == ["user", "model", "user"]
    assert params["config"]["temperature"] == 0.2
    assert params["config"]["system_instruction"] == "sys"


# Streaming adapters against fake SDK clients


class FakeAnthropicStream:
    def __init__(self, texts: list[str], stop_reason: str):
        self.texts = texts
        self.stop_reason = stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def generate():
            for text in self.texts:
                yield text

        return generate()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop_reason)


class FakeMessagesAPI:
    def __init__(self, stream):
        self.calls: list[dict] = []
        self._stream = stream

    def stream(self, **params):
        self.calls.append(params)
        return self._stream


def test_claude_stream_uses_beta_endpoint_and_flags_refusals():
    beta = FakeMessagesAPI(FakeAnthropicStream(["Partial "], "refusal"))
    plain = FakeMessagesAPI(FakeAnthropicStream([], "end_turn"))
    client = SimpleNamespace(messages=plain, beta=SimpleNamespace(messages=beta))
    chat = AnthropicChat(chat_model(ANTHROPIC, "claude-sonnet-5-5"), "k", client=client)

    assert collect(chat.stream("sys", HISTORY)) == ["Partial ", REFUSAL_NOTE]
    assert len(beta.calls) == 1 and not plain.calls
    assert beta.calls[0]["fallbacks"] == "default"


def test_claude_haiku_streams_through_the_plain_endpoint():
    plain = FakeMessagesAPI(FakeAnthropicStream(["Hello", " there"], "end_turn"))
    client = SimpleNamespace(messages=plain, beta=SimpleNamespace(messages=None))
    chat = AnthropicChat(chat_model(ANTHROPIC, "claude-haiku-4-5"), "k", client=client)
    assert collect(chat.stream("sys", HISTORY)) == ["Hello", " there"]


def test_openai_stream_yields_text_deltas_and_raises_on_failure():
    events = [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(type="response.output_text.delta", delta="RAG "),
        SimpleNamespace(type="response.output_text.delta", delta="grounds answers."),
        SimpleNamespace(
            type="response.failed", response=SimpleNamespace(error=SimpleNamespace(message="boom"))
        ),
    ]

    async def create(**params):
        async def generate():
            for event in events:
                yield event

        return generate()

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    chat = OpenAIChat(chat_model(OPENAI, "gpt-5-mini"), "k", client=client)

    received: list[str] = []

    async def run():
        async for piece in chat.stream("sys", HISTORY):
            received.append(piece)

    with pytest.raises(ProviderError, match="boom"):
        asyncio.run(run())
    assert received == ["RAG ", "grounds answers."]


# API keys


def _request(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw})


def test_header_keys_override_server_keys():
    settings = Settings(
        _env_file=None, openai_api_key="server-openai", anthropic_api_key=None, google_api_key=None
    )
    keys = resolve_keys(_request({"X-Anthropic-Key": "user-anthropic", "X-OpenAI-Key": " "}), settings)
    assert keys == ApiKeys(openai="server-openai", anthropic="user-anthropic", google=None)


def test_missing_key_names_the_env_variable():
    with pytest.raises(ProviderError) as info:
        ApiKeys().for_provider(GOOGLE)
    assert info.value.status_code == 400
    assert "GOOGLE_API_KEY" in info.value.message
