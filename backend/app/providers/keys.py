from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.providers.catalog import ANTHROPIC, GOOGLE, MOCK, OPENAI, PROVIDER_LABELS
from app.providers.errors import ProviderError

ENV_NAMES = {
    OPENAI: "OPENAI_API_KEY",
    ANTHROPIC: "ANTHROPIC_API_KEY",
    GOOGLE: "GOOGLE_API_KEY",
}

# Keys a user enters in the UI travel per request in these headers and are never
# stored server-side. They take precedence over the server's own keys.
HEADER_NAMES = {
    OPENAI: "x-openai-key",
    ANTHROPIC: "x-anthropic-key",
    GOOGLE: "x-google-key",
}


@dataclass(frozen=True)
class ApiKeys:
    openai: str | None = None
    anthropic: str | None = None
    google: str | None = None

    def for_provider(self, provider: str) -> str:
        if provider == MOCK:
            return ""
        key = getattr(self, provider, None)
        if not key:
            label = PROVIDER_LABELS.get(provider, provider)
            raise ProviderError(
                f"No {label} API key. Add one in Settings, or set {ENV_NAMES[provider]} on the server.",
                status_code=400,
            )
        return key


def resolve_keys(request: Request, settings: Settings) -> ApiKeys:
    def pick(provider: str, server_value: str | None) -> str | None:
        header = request.headers.get(HEADER_NAMES[provider], "").strip()
        return header or server_value

    return ApiKeys(
        openai=pick(OPENAI, settings.openai_api_key),
        anthropic=pick(ANTHROPIC, settings.anthropic_api_key),
        google=pick(GOOGLE, settings.google_api_key),
    )
