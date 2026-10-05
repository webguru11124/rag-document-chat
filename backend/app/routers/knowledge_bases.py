import asyncio
import hashlib
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status

from app.config import Settings
from app.deps import get_app_settings, get_store
from app.loaders import SUPPORTED_EXTENSIONS, UnreadableFileError, UnsupportedFileError, extension, load
from app.providers.catalog import embedding_model, providers
from app.providers.embeddings import get_embedder
from app.providers.keys import resolve_keys
from app.retrieval import split
from app.schemas import DocumentOut, KnowledgeBaseCreate, KnowledgeBaseOut, PassageOut, SearchRequest
from app.store import DuplicateDocumentError, KnowledgeBase, Store

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge bases"])

READ_CHUNK_BYTES = 1024 * 1024


async def _knowledge_base(store: Store, knowledge_base_id: str) -> KnowledgeBase:
    kb = await asyncio.to_thread(store.get_knowledge_base, knowledge_base_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found.")
    return kb


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(store: Store = Depends(get_store)):
    return [kb.to_dict() for kb in await asyncio.to_thread(store.list_knowledge_bases)]


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
):
    if body.embedding_provider not in providers(settings.enable_mock_provider):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown provider '{body.embedding_provider}'.")
    model = embedding_model(body.embedding_provider, body.embedding_model)
    if model is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{body.embedding_model or body.embedding_provider}' isn't an available embedding model.",
        )
    kb = await asyncio.to_thread(
        store.create_knowledge_base, body.name, body.description, model.provider, model.id
    )
    return kb.to_dict()


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(knowledge_base_id: str, store: Store = Depends(get_store)):
    return (await _knowledge_base(store, knowledge_base_id)).to_dict()


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(knowledge_base_id: str, store: Store = Depends(get_store)):
    if not await asyncio.to_thread(store.delete_knowledge_base, knowledge_base_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentOut])
async def list_documents(knowledge_base_id: str, store: Store = Depends(get_store)):
    kb = await _knowledge_base(store, knowledge_base_id)
    return [doc.to_dict() for doc in await asyncio.to_thread(store.list_documents, kb.id)]


@router.post(
    "/{knowledge_base_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile,
    request: Request,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
):
    """Parse, chunk, embed and index one file."""
    kb = await _knowledge_base(store, knowledge_base_id)
    filename = PurePath(file.filename or "upload").name
    if extension(filename) not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"{filename}: only {', '.join(SUPPORTED_EXTENSIONS)} files are supported.",
        )

    data = await _read_limited(file, settings.max_upload_bytes, filename, settings.max_upload_mb)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{filename} is empty.")

    digest = hashlib.sha256(data).hexdigest()
    existing = await asyncio.to_thread(store.find_document_by_hash, kb.id, digest)
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{filename} is already in this knowledge base as {existing.filename}."
        )

    embedder = get_embedder(
        kb.embedding_provider,
        kb.embedding_model,
        resolve_keys(request, settings),
        mock_enabled=settings.enable_mock_provider,
    )
    try:
        segments = await asyncio.to_thread(load, filename, data)
    except UnsupportedFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except UnreadableFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    chunks = split(segments, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"No text could be extracted from {filename}. Scanned PDFs need OCR first.",
        )

    vectors = await embedder.embed_documents([chunk.text for chunk in chunks])
    pages = max((s.page for s in segments if s.page is not None), default=None)
    try:
        record = await asyncio.to_thread(
            store.add_document,
            kb.id,
            filename=filename,
            size_bytes=len(data),
            sha256=digest,
            pages=pages,
            chunks=chunks,
            vectors=vectors,
        )
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{filename} is already in this knowledge base."
        ) from exc
    return record.to_dict()


@router.delete("/{knowledge_base_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(knowledge_base_id: str, document_id: str, store: Store = Depends(get_store)):
    if not await asyncio.to_thread(store.delete_document, knowledge_base_id, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{knowledge_base_id}/search", response_model=list[PassageOut])
async def search(
    knowledge_base_id: str,
    body: SearchRequest,
    request: Request,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
):
    """Retrieval only, without an LLM call. Handy for tuning and debugging."""
    kb = await _knowledge_base(store, knowledge_base_id)
    embedder = get_embedder(
        kb.embedding_provider,
        kb.embedding_model,
        resolve_keys(request, settings),
        mock_enabled=settings.enable_mock_provider,
    )
    vector = await embedder.embed_query(body.query)
    passages = await asyncio.to_thread(store.search, kb.id, vector, body.top_k, body.search_type)
    return [p.to_dict() for p in passages]


async def _read_limited(file: UploadFile, limit: int, filename: str, limit_mb: int) -> bytes:
    data = bytearray()
    while chunk := await file.read(READ_CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, f"{filename} is larger than the {limit_mb} MB limit."
            )
    return bytes(data)
