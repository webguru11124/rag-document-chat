from typing import Literal

from pydantic import BaseModel, Field, field_validator


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    embedding_provider: str
    embedding_model: str | None = None

    @field_validator("name", "description")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    embedding_provider: str
    embedding_model: str
    created_at: str
    document_count: int
    chunk_count: int


class DocumentOut(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    size_bytes: int
    pages: int | None
    chunk_count: int
    characters: int
    created_at: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    search_type: Literal["similarity", "mmr"] = "mmr"


class PassageOut(BaseModel):
    number: int
    document_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20000)


class ChatRequest(BaseModel):
    knowledge_base_id: str
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=100)
    provider: str
    model: str = Field(min_length=1, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_k: int | None = Field(default=None, ge=1, le=50)
    search_type: Literal["similarity", "mmr"] = "mmr"

    @field_validator("messages")
    @classmethod
    def ends_with_question(cls, messages: list[ChatMessageIn]) -> list[ChatMessageIn]:
        if messages[-1].role != "user" or not messages[-1].content.strip():
            raise ValueError("The last message must be a non-empty user message.")
        return messages
