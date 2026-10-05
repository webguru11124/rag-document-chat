import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.deps import get_app_settings, get_store
from app.providers.chat import Message, chat_client
from app.providers.embeddings import get_embedder
from app.providers.keys import resolve_keys
from app.rag import answer_stream
from app.schemas import ChatRequest
from app.store import Store

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_class=StreamingResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
):
    """Answer the last user message from the knowledge base, streamed as server-sent events."""
    kb = await asyncio.to_thread(store.get_knowledge_base, body.knowledge_base_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found.")
    if kb.document_count == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a document to this knowledge base first.")

    # Build both clients before streaming starts, so a missing key or unknown model is
    # a plain HTTP error rather than an error event in the middle of a stream.
    keys = resolve_keys(request, settings)
    mock = settings.enable_mock_provider
    model_client = chat_client(body.provider, body.model, keys, mock_enabled=mock)
    embedder = get_embedder(kb.embedding_provider, kb.embedding_model, keys, mock_enabled=mock)

    stream = answer_stream(
        store=store,
        knowledge_base_id=kb.id,
        embedder=embedder,
        chat=model_client,
        messages=[Message(m.role, m.content) for m in body.messages],
        top_k=min(body.top_k or settings.default_top_k, settings.max_top_k),
        search_type=body.search_type,
        temperature=body.temperature,
        max_history=settings.max_history_messages,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
