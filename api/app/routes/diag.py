"""GET /api/_diag/rag — read-only RAG diagnostic.

Runs a live retrieval in the request thread (the real failing path) and reports
what came back, plus the last swallowed query-time error. Temporary: lets us see
why production retrieval returns [] without crashing the chat stream. Remove once
the RAG outage is resolved.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["diag"])

_PROBE_QUERY = "How do auctions work?"


@router.get("/_diag/rag")
def diag_rag(request: Request) -> dict:
    rag = request.app.state.rag
    chunks = rag.retrieve(_PROBE_QUERY, k=3)
    return {
        "store": type(rag).__name__,
        "ready": getattr(rag, "ready", None),
        "thread": threading.current_thread().name,
        "query": _PROBE_QUERY,
        "retrieved": [
            {"source_id": c.source_id, "score": c.score} for c in chunks
        ],
        "last_error": getattr(rag, "last_error", None),
    }
