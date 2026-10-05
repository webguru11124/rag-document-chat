"""The question-answering pipeline, streamed as server-sent events.

1. If there is earlier conversation, ask the model to rewrite the latest message as a
   standalone search query ("what about its price?" -> "price of the X200 router").
2. Embed that query and retrieve passages from the knowledge base.
3. Send the passages, numbered, with the question and stream the answer back.

Events: `sources` (the retrieved passages, sent first so the UI can show them while
the answer streams), `token` (answer text deltas), `done`, and `error`.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.prompts import (
    ANSWER_SYSTEM,
    CONDENSE_SYSTEM,
    CONTEXT_CLOSE,
    CONTEXT_OPEN,
    CONVERSATION_PREFIX,
    LATEST_PREFIX,
    QUESTION_PREFIX,
)
from app.providers.chat import ChatClient, Message
from app.providers.embeddings import Embedder
from app.providers.errors import ProviderError
from app.retrieval import Passage
from app.store import SearchType, Store

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 1000


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_context(passages: list[Passage]) -> str:
    if not passages:
        return "(no matching passages)"
    blocks = []
    for passage in passages:
        where = passage.filename + (f", page {passage.page}" if passage.page else "")
        blocks.append(f"[{passage.number}] source: {where}\n{passage.text}")
    return "\n\n".join(blocks)


def answer_messages(history: list[Message], question: str, passages: list[Passage]) -> list[Message]:
    prompt = f"{CONTEXT_OPEN}\n{format_context(passages)}\n{CONTEXT_CLOSE}\n\n{QUESTION_PREFIX}{question}"
    return [*history, Message("user", prompt)]


def condense_messages(history: list[Message], question: str) -> list[Message]:
    lines = []
    for message in history:
        speaker = "User" if message.role == "user" else "Assistant"
        text = " ".join(message.content.split())
        lines.append(f"{speaker}: {text[:800]}")
    prompt = f"{CONVERSATION_PREFIX}\n" + "\n".join(lines) + f"\n\n{LATEST_PREFIX}{question}"
    return [Message("user", prompt)]


def trim_history(messages: list[Message], limit: int) -> list[Message]:
    history = [m for m in messages if m.content.strip()][-limit:] if limit > 0 else []
    # Providers expect the conversation to open with a user turn.
    while history and history[0].role != "user":
        history = history[1:]
    return history


async def answer_stream(
    *,
    store: Store,
    knowledge_base_id: str,
    embedder: Embedder,
    chat: ChatClient,
    messages: list[Message],
    top_k: int,
    search_type: SearchType,
    temperature: float | None,
    max_history: int,
) -> AsyncIterator[str]:
    question = messages[-1].content.strip()
    history = trim_history(messages[:-1], max_history)
    try:
        query = question
        if history:
            rewritten = (await chat.complete(CONDENSE_SYSTEM, condense_messages(history, question))).strip()
            if rewritten:
                query = rewritten[:MAX_QUERY_CHARS]

        query_vector = await embedder.embed_query(query)
        passages = await asyncio.to_thread(store.search, knowledge_base_id, query_vector, top_k, search_type)
        yield sse("sources", {"query": query, "sources": [p.to_dict() for p in passages]})

        prompt = answer_messages(history, question, passages)
        async for text in chat.stream(ANSWER_SYSTEM, prompt, temperature):
            yield sse("token", {"text": text})
        yield sse("done", {})
    except ProviderError as exc:
        yield sse("error", {"message": exc.message})
    except Exception:
        logger.exception("Answering failed")
        yield sse("error", {"message": "Something went wrong while answering. Check the server logs."})
