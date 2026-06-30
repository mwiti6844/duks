"""Application factory. Tests inject a fake LLM provider; production fails fast when
both real keys are absent (config.load_settings). Heavy init (seed + embeddings) runs
in a background thread so /api/health can answer immediately."""
from __future__ import annotations

import threading
from pathlib import Path

from alembic import command
from alembic.config import Config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.deps import Deps
from .agents.graph import build_graph
from .auth.routes import router as auth_router
from .config import Settings, load_settings
from .db.engine import SessionLocal, create_all
from .db.seed import seed_all
from .health import Readiness
from .llm.provider import LLMProvider, build_provider
from .memory.session import SessionStore
from .rag.store import RagStore
from .routes.bids import router as bids_router
from .routes.catalog import router as catalog_router
from .routes.chat import router as chat_router
from .routes.financing import router as financing_router
from .routes.health import router as health_router
from .routes.listings import router as listings_router
from .routes.listing_drafts import router as listing_drafts_router
from .routes.session import router as session_router


def _background_init(app: FastAPI) -> None:
    try:
        create_all()
        migration_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        migration_config.set_main_option(
            "script_location", str(Path(__file__).parents[1] / "migrations")
        )
        command.upgrade(migration_config, "head")
        with SessionLocal() as db:
            seed_all(db)
        app.state.rag.initialize()
        app.state.readiness.mark_ready()
    except Exception as exc:  # pragma: no cover - surfaced via /api/health
        app.state.readiness.mark_error(str(exc))


def create_app(
    *,
    settings: Settings | None = None,
    llm_provider: LLMProvider | None = None,
    rag_store: RagStore | None = None,
    allow_fake: bool = False,
    eager_init: bool = False,
) -> FastAPI:
    settings = settings or load_settings(allow_fake=allow_fake or llm_provider is not None)

    app = FastAPI(title="CarDuka AI Agent Demo API")
    # Permissive CORS is fine: only the trusted Next.js BFF reaches this private service.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    rag = rag_store or RagStore()
    sessions = SessionStore(
        settings.redis_url, allow_fallback=settings.allow_in_memory_sessions
    )
    provider = llm_provider or build_provider(settings)

    app.state.settings = settings
    app.state.readiness = Readiness()
    app.state.rag = rag
    app.state.sessions = sessions
    app.state.deps = Deps(
        db_factory=SessionLocal,
        rag=rag,
        llm=provider,
        sessions=sessions,
        settings=settings,
    )
    app.state.graph = build_graph()

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(chat_router)
    app.include_router(bids_router)
    app.include_router(financing_router)
    app.include_router(listings_router)
    app.include_router(listing_drafts_router)
    app.include_router(session_router)

    if eager_init:
        _background_init(app)
    else:
        @app.on_event("startup")
        def _startup() -> None:
            threading.Thread(target=_background_init, args=(app,), daemon=True).start()

    return app
