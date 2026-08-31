"""App factory. Middleware order and lifespan wiring live here."""

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.api.routes import admin, chat, feedback, health, memories, threads
from app.config import settings
from app.logging import configure_logging, get_logger
from app.memory.checkpointer import get_checkpointer
from app.memory.store import get_store
from app.models.base import session_factory
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import Reranker

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with AsyncExitStack() as stack:
        # Fail independently: one loses thread memory, the other long-term memory.
        checkpointer = store = None
        try:
            checkpointer = await stack.enter_async_context(get_checkpointer())
        except Exception as exc:
            log.error("checkpointer_unavailable", error=str(exc), impact="no thread memory")
        try:
            store = await stack.enter_async_context(get_store())
        except Exception as exc:
            log.error("store_unavailable", error=str(exc), impact="no long-term memory")

        app.state.checkpointer = checkpointer
        app.state.store = store
        app.state.reranker = Reranker()

        # The graph holds a session-scoped retriever per request, so build lazily there.
        from app.graph.build import build_graph

        class _SessionRetriever:
            """`Retriever` that opens a session per call, so the graph compiles once."""

            async def retrieve(self, query, user_groups, filters=None, limit=None):
                """See `Retriever.retrieve`."""
                async with session_factory() as session:
                    return await HybridRetriever(session).retrieve(
                        query, user_groups, filters, limit
                    )

        app.state.graph = build_graph(
            _SessionRetriever(),
            reranker=app.state.reranker,
            checkpointer=checkpointer,
            store=store,
        )
        log.info("startup_complete", auth_disabled=settings.auth_disabled)
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ferret",
        description="Enterprise document assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.auth_disabled else [settings.api_base_url],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(threads.router)
    app.include_router(memories.router)
    app.include_router(feedback.router)
    app.include_router(admin.router)

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
