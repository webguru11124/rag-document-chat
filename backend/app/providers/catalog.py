"""Which providers and models the app offers, and what each model accepts.

Model families differ in the request parameters they take: OpenAI's GPT-5 models
reject `temperature` and take a reasoning effort instead, Claude 5.5 models take an
effort level and reject sampling parameters, Gemini takes a plain temperature. The
flags below drive how each provider adapter builds its request.
"""

from dataclasses import asdict, dataclass

OPENAI = "openai"
ANTHROPIC = "anthropic"
GOOGLE = "google"
MOCK = "mock"

PROVIDER_LABELS = {
    OPENAI: "OpenAI",
    ANTHROPIC: "Anthropic",
    GOOGLE: "Google Gemini",
    MOCK: "Mock (offline)",
}


@dataclass(frozen=True)
class ChatModel:
    id: str
    label: str
    provider: str
    temperature: bool = False  # accepts a temperature setting
    reasoning: bool = False  # OpenAI reasoning model: send `reasoning.effort`
    effort: bool = False  # Claude model that takes `output_config.effort`
    fallbacks: bool = False  # Claude model that supports server-side refusal fallbacks

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    label: str
    provider: str
    dimensions: int

    def to_dict(self) -> dict:
        return asdict(self)


CHAT_MODELS: list[ChatModel] = [
    ChatModel("gpt-5.4-mini", "GPT-5.4 mini", OPENAI, reasoning=True),
    ChatModel("gpt-5-mini", "GPT-5 mini", OPENAI, reasoning=True),
    ChatModel("gpt-5-nano", "GPT-5 nano", OPENAI, reasoning=True),
    ChatModel("gpt-4o-mini", "GPT-4o mini", OPENAI, temperature=True),
    ChatModel("claude-opus-5-5", "Claude Opus 5.5", ANTHROPIC, effort=True, fallbacks=True),
    ChatModel("claude-sonnet-5-5", "Claude Sonnet 5.5", ANTHROPIC, effort=True, fallbacks=True),
    ChatModel("claude-haiku-4-5", "Claude Haiku 4.5", ANTHROPIC),
    ChatModel("gemini-2.5-flash", "Gemini 2.5 Flash", GOOGLE, temperature=True),
    ChatModel("gemini-2.5-pro", "Gemini 2.5 Pro", GOOGLE, temperature=True),
    ChatModel("mock-extractive", "Extractive answers", MOCK),
]

EMBEDDING_MODELS: list[EmbeddingModel] = [
    EmbeddingModel("text-embedding-3-small", "text-embedding-3-small", OPENAI, 1536),
    EmbeddingModel("text-embedding-3-large", "text-embedding-3-large", OPENAI, 3072),
    EmbeddingModel("gemini-embedding-001", "gemini-embedding-001 (768-d)", GOOGLE, 768),
    EmbeddingModel("mock-hashing", "Hashed bag-of-words", MOCK, 384),
]


def chat_model(provider: str, model_id: str) -> ChatModel:
    """Look up a catalog model, or describe a custom model ID conservatively."""
    for model in CHAT_MODELS:
        if model.provider == provider and model.id == model_id:
            return model
    if provider == OPENAI:
        # GPT-5 family and o-series models are reasoning models.
        reasoning = model_id.startswith(("gpt-5", "o1", "o3", "o4"))
        return ChatModel(model_id, model_id, provider, temperature=not reasoning, reasoning=reasoning)
    if provider == GOOGLE:
        return ChatModel(model_id, model_id, provider, temperature=True)
    # Anthropic and anything else: send no optional parameters.
    return ChatModel(model_id, model_id, provider)


def embedding_model(provider: str, model_id: str | None) -> EmbeddingModel | None:
    for model in EMBEDDING_MODELS:
        if model.provider == provider and (model_id is None or model.id == model_id):
            return model
    return None


def providers(mock_enabled: bool) -> list[str]:
    ids = [OPENAI, ANTHROPIC, GOOGLE]
    return ids + [MOCK] if mock_enabled else ids
