from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.providers.errors import ProviderError
from app.routers import chat, knowledge_bases, meta
from app.store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = Store(settings.data_dir)
        yield

    app = FastAPI(
        title="RAG Document Chat API",
        version="1.0.0",
        description="Upload documents into knowledge bases and chat with them.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ProviderError)
    async def provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    app.include_router(meta.router)
    app.include_router(knowledge_bases.router)
    app.include_router(chat.router)
    return app


app = create_app()
