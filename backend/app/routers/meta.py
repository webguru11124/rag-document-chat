from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_app_settings
from app.loaders import SUPPORTED_EXTENSIONS
from app.providers.catalog import (
    ANTHROPIC,
    CHAT_MODELS,
    EMBEDDING_MODELS,
    GOOGLE,
    MOCK,
    OPENAI,
    PROVIDER_LABELS,
    providers,
)

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
def config(settings: Settings = Depends(get_app_settings)) -> dict:
    """What the UI needs to render pickers: providers, models, defaults and limits."""
    server_key = {
        OPENAI: bool(settings.openai_api_key),
        ANTHROPIC: bool(settings.anthropic_api_key),
        GOOGLE: bool(settings.google_api_key),
        MOCK: True,
    }
    provider_ids = providers(settings.enable_mock_provider)

    def first_ready(candidates: list[str]) -> str:
        for provider in candidates:
            if server_key[provider]:
                return provider
        return MOCK if settings.enable_mock_provider else candidates[0]

    chat_provider = first_ready([OPENAI, ANTHROPIC, GOOGLE])
    embedding_provider = first_ready([OPENAI, GOOGLE])

    return {
        "providers": [
            {
                "id": provider,
                "label": PROVIDER_LABELS[provider],
                "requires_key": provider != MOCK,
                "server_key": server_key[provider],
                "chat_models": [m.to_dict() for m in CHAT_MODELS if m.provider == provider],
                "embedding_models": [m.to_dict() for m in EMBEDDING_MODELS if m.provider == provider],
            }
            for provider in provider_ids
        ],
        "defaults": {
            "chat_provider": chat_provider,
            "chat_model": next(m.id for m in CHAT_MODELS if m.provider == chat_provider),
            "embedding_provider": embedding_provider,
            "embedding_model": next(m.id for m in EMBEDDING_MODELS if m.provider == embedding_provider),
            "top_k": settings.default_top_k,
            "search_type": "mmr",
        },
        "limits": {
            "max_upload_mb": settings.max_upload_mb,
            "max_top_k": settings.max_top_k,
            "extensions": list(SUPPORTED_EXTENSIONS),
        },
        "mock_enabled": settings.enable_mock_provider,
    }
