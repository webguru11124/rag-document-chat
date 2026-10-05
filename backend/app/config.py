from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or `backend/.env`."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY")
    )

    data_dir: Path = Path("data")
    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:3000"

    # A keyless provider that embeds with hashed bag-of-words vectors and answers
    # extractively. Meant for local development, demos and tests.
    enable_mock_provider: bool = False

    max_upload_mb: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 150
    default_top_k: int = 5
    max_top_k: int = 12
    # How many earlier chat messages are sent along with a new question.
    max_history_messages: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
