"""Persistence: knowledge-base and document records in SQLite, vectors in Chroma.

Each knowledge base gets its own Chroma collection, because a collection holds
vectors of one dimension and each knowledge base is tied to one embedding model.
"""

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from app.retrieval import Chunk, Passage, mmr

SearchType = Literal["similarity", "mmr"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    pages INTEGER,
    chunk_count INTEGER NOT NULL,
    characters INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (knowledge_base_id, sha256)
);
CREATE INDEX IF NOT EXISTS documents_kb ON documents(knowledge_base_id);
"""

CHROMA_BATCH = 1000


class DuplicateDocumentError(Exception):
    pass


@dataclass(frozen=True)
class KnowledgeBase:
    id: str
    name: str
    description: str
    embedding_provider: str
    embedding_model: str
    created_at: str
    document_count: int = 0
    chunk_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    knowledge_base_id: str
    filename: str
    size_bytes: int
    sha256: str
    pages: int | None
    chunk_count: int
    characters: int
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "app.db"
        self.chroma = chromadb.PersistentClient(
            path=str(data_dir / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
        )
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _collection(self, knowledge_base_id: str):
        return self.chroma.get_or_create_collection(
            name=f"kb_{knowledge_base_id}",
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,
        )

    # Knowledge bases

    def list_knowledge_bases(self) -> list[KnowledgeBase]:
        with self._db() as db:
            rows = db.execute(
                """
                SELECT kb.*, COUNT(d.id) AS document_count, COALESCE(SUM(d.chunk_count), 0) AS chunk_count
                FROM knowledge_bases kb LEFT JOIN documents d ON d.knowledge_base_id = kb.id
                GROUP BY kb.id ORDER BY kb.created_at DESC, kb.name
                """
            ).fetchall()
        return [KnowledgeBase(**dict(row)) for row in rows]

    def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBase | None:
        with self._db() as db:
            row = db.execute(
                """
                SELECT kb.*, COUNT(d.id) AS document_count, COALESCE(SUM(d.chunk_count), 0) AS chunk_count
                FROM knowledge_bases kb LEFT JOIN documents d ON d.knowledge_base_id = kb.id
                WHERE kb.id = ? GROUP BY kb.id
                """,
                (knowledge_base_id,),
            ).fetchone()
        return KnowledgeBase(**dict(row)) if row else None

    def create_knowledge_base(
        self, name: str, description: str, embedding_provider: str, embedding_model: str
    ) -> KnowledgeBase:
        kb = KnowledgeBase(
            id=uuid.uuid4().hex,
            name=name,
            description=description,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            created_at=_now(),
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO knowledge_bases"
                " (id, name, description, embedding_provider, embedding_model, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (kb.id, kb.name, kb.description, kb.embedding_provider, kb.embedding_model, kb.created_at),
            )
        self._collection(kb.id)
        return kb

    def delete_knowledge_base(self, knowledge_base_id: str) -> bool:
        with self._db() as db:
            deleted = db.execute("DELETE FROM knowledge_bases WHERE id = ?", (knowledge_base_id,)).rowcount
        if deleted:
            with suppress(Exception):  # the collection may already be gone
                self.chroma.delete_collection(f"kb_{knowledge_base_id}")
        return bool(deleted)

    # Documents

    def list_documents(self, knowledge_base_id: str) -> list[DocumentRecord]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM documents WHERE knowledge_base_id = ? ORDER BY created_at DESC, filename",
                (knowledge_base_id,),
            ).fetchall()
        return [DocumentRecord(**dict(row)) for row in rows]

    def find_document_by_hash(self, knowledge_base_id: str, sha256: str) -> DocumentRecord | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE knowledge_base_id = ? AND sha256 = ?",
                (knowledge_base_id, sha256),
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def add_document(
        self,
        knowledge_base_id: str,
        *,
        filename: str,
        size_bytes: int,
        sha256: str,
        pages: int | None,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> DocumentRecord:
        record = DocumentRecord(
            id=uuid.uuid4().hex,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            size_bytes=size_bytes,
            sha256=sha256,
            pages=pages,
            chunk_count=len(chunks),
            characters=sum(len(chunk.text) for chunk in chunks),
            created_at=_now(),
        )
        collection = self._collection(knowledge_base_id)
        ids = [f"{record.id}:{chunk.index}" for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            metadata = {"document_id": record.id, "filename": filename, "chunk_index": chunk.index}
            if chunk.page is not None:
                metadata["page"] = chunk.page
            metadatas.append(metadata)

        for start in range(0, len(chunks), CHROMA_BATCH):
            end = start + CHROMA_BATCH
            collection.add(
                ids=ids[start:end],
                embeddings=vectors[start:end],
                documents=[chunk.text for chunk in chunks[start:end]],
                metadatas=metadatas[start:end],
            )
        try:
            with self._db() as db:
                db.execute(
                    "INSERT INTO documents (id, knowledge_base_id, filename, size_bytes, sha256, pages,"
                    " chunk_count, characters, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.id,
                        record.knowledge_base_id,
                        record.filename,
                        record.size_bytes,
                        record.sha256,
                        record.pages,
                        record.chunk_count,
                        record.characters,
                        record.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            collection.delete(where={"document_id": record.id})
            raise DuplicateDocumentError(filename) from exc
        return record

    def delete_document(self, knowledge_base_id: str, document_id: str) -> bool:
        with self._db() as db:
            deleted = db.execute(
                "DELETE FROM documents WHERE id = ? AND knowledge_base_id = ?",
                (document_id, knowledge_base_id),
            ).rowcount
        if deleted:
            self._collection(knowledge_base_id).delete(where={"document_id": document_id})
        return bool(deleted)

    # Search

    def search(
        self, knowledge_base_id: str, query_vector: list[float], top_k: int, search_type: SearchType
    ) -> list[Passage]:
        collection = self._collection(knowledge_base_id)
        count = collection.count()
        if count == 0:
            return []

        use_mmr = search_type == "mmr"
        include = ["documents", "metadatas", "distances"] + (["embeddings"] if use_mmr else [])
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=min(count, max(top_k * 4, 20) if use_mmr else top_k),
            include=include,
        )
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        if use_mmr:
            order = mmr(np.asarray(query_vector), np.asarray(result["embeddings"][0]), top_k)
        else:
            order = list(range(len(documents)))

        passages = []
        for number, i in enumerate(order, 1):
            metadata = metadatas[i]
            passages.append(
                Passage(
                    number=number,
                    document_id=str(metadata["document_id"]),
                    filename=str(metadata["filename"]),
                    page=int(metadata["page"]) if "page" in metadata else None,
                    chunk_index=int(metadata["chunk_index"]),
                    text=documents[i],
                    score=round(1.0 - float(distances[i]), 4),
                )
            )
        return passages
