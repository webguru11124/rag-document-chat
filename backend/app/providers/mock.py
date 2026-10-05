"""A keyless provider for local development, demos and tests.

`MockEmbedder` hashes words into a fixed-size vector, so passages that share words
with the query score higher. `MockChat` answers extractively: it picks the sentence
from each retrieved passage that overlaps most with the question and cites it.
"""

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator

import numpy as np

from app.prompts import CONTEXT_CLOSE, CONTEXT_OPEN, CONVERSATION_PREFIX, LATEST_PREFIX, QUESTION_PREFIX
from app.providers.catalog import ChatModel, EmbeddingModel
from app.providers.chat import Message

STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from has have how i if in into is it its
    me my no not of on or our so than that the their them then there these they this to
    was we were what when where which who why will with you your about after also any
    been before being both each more most other over same some such only own very""".split()  # noqa: SIM905
)

WORD = re.compile(r"[a-z0-9]+")
SUFFIXES = ("ing", "ed", "es", "s", "e")


def stem(word: str) -> str:
    """Crude suffix stripping, so "facing" and "face" count as the same word."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in WORD.findall(text.lower()) if len(w) > 1 and w not in STOPWORDS]


class MockEmbedder:
    def __init__(self, model: EmbeddingModel):
        self.model = model

    def _vector(self, text: str) -> list[float]:
        vector = np.zeros(self.model.dimensions, dtype=np.float64)
        for word in tokens(text):
            digest = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
            vector[digest % self.model.dimensions] += 1.0 if digest & (1 << 63) else -1.0
        norm = np.linalg.norm(vector)
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return (vector / norm).tolist()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class MockChat:
    TOKEN_DELAY_SECONDS = 0.01

    def __init__(self, model: ChatModel):
        self.model = model

    async def stream(
        self, system: str, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        answer = extractive_answer(messages[-1].content)
        for piece in re.findall(r"\S+\s*", answer):
            await asyncio.sleep(self.TOKEN_DELAY_SECONDS)
            yield piece

    async def complete(self, system: str, messages: list[Message]) -> str:
        # Used to condense follow-ups: search with the latest message plus the
        # previous user question, which is usually what a pronoun refers to.
        prompt = messages[-1].content
        latest = prompt.split(LATEST_PREFIX, 1)[-1].strip()
        earlier_user_lines = [
            line[len("User: ") :]
            for line in prompt.split(CONVERSATION_PREFIX, 1)[-1].splitlines()
            if line.startswith("User: ")
        ]
        return f"{latest} {earlier_user_lines[-1]}" if earlier_user_lines else latest


def extractive_answer(prompt: str) -> str:
    question = prompt.split(QUESTION_PREFIX, 1)[-1].strip()
    context = prompt.split(CONTEXT_OPEN, 1)[-1].split(CONTEXT_CLOSE, 1)[0]
    passages = re.findall(
        r"^\[(\d+)\] source:[^\n]*\n(.*?)(?=^\[\d+\] source:|\Z)", context, flags=re.S | re.M
    )
    if not passages:
        return "I couldn't find anything about that in the uploaded documents."

    question_words = set(tokens(question))
    picked: list[tuple[str, str]] = []
    for number, text in passages[:3]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 20]
        overlap = {s: len(question_words & set(tokens(s))) for s in sentences}
        # Up to two best-matching sentences per passage, in their original order.
        best = sorted((s for s in sentences if overlap[s]), key=lambda s: -overlap[s])[:2]
        picked.extend((number, s) for s in sentences if s in best)

    if not picked:
        return "I couldn't find anything about that in the uploaded documents."
    lines = [f"- {sentence} [{number}]" for number, sentence in picked]
    return (
        "Here's what the documents say:\n\n"
        + "\n".join(lines)
        + "\n\n_Mock provider: these are extracted sentences, not a generated answer. "
        "Add an API key in Settings for real answers._"
    )
