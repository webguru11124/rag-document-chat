"""Chunking and result re-ranking, kept free of I/O so they're easy to test."""

from dataclasses import asdict, dataclass

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.loaders import Segment


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int | None
    index: int


@dataclass(frozen=True)
class Passage:
    number: int  # 1-based position in the prompt; what citations like [2] refer to
    document_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float  # cosine similarity to the query

    def to_dict(self) -> dict:
        return asdict(self)


def split(segments: list[Segment], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator="end",
    )
    chunks: list[Chunk] = []
    for segment in segments:
        for piece in splitter.split_text(segment.text):
            piece = piece.strip()
            if piece:
                chunks.append(Chunk(piece, segment.page, len(chunks)))
    return chunks


def mmr(query: np.ndarray, candidates: np.ndarray, k: int, diversity: float = 0.5) -> list[int]:
    """Maximal marginal relevance: pick relevant candidates that don't repeat each other.

    Returns indices into `candidates`. `diversity` 0 ranks purely by relevance; higher
    values penalise candidates similar to ones already picked.
    """
    if len(candidates) == 0 or k <= 0:
        return []
    query = query / (np.linalg.norm(query) or 1.0)
    norms = np.linalg.norm(candidates, axis=1, keepdims=True)
    candidates = candidates / np.where(norms == 0, 1.0, norms)

    relevance = candidates @ query
    selected = [int(np.argmax(relevance))]
    while len(selected) < min(k, len(candidates)):
        redundancy = (candidates @ candidates[selected].T).max(axis=1)
        scores = (1 - diversity) * relevance - diversity * redundancy
        scores[selected] = -np.inf
        selected.append(int(np.argmax(scores)))
    return selected
