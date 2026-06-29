"""Shared test fixtures. Uses a fresh SQLite file per session, the fake LLM provider,
and eager init so the app is ready immediately."""
from __future__ import annotations

import os
import tempfile

import pytest

# Isolate the test DB before any app import touches the engine.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["SQLITE_PATH"] = _tmp.name
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("BID_SIGNING_SECRET", "test-bid-secret")
os.environ.pop("REDIS_URL", None)  # force in-memory session fallback in tests

from fastapi.testclient import TestClient  # noqa: E402

from app.factory import create_app  # noqa: E402
from app.llm.provider import FakeProvider  # noqa: E402
from app.rag.store import RetrievedChunk  # noqa: E402
from app.seed_data.faqs import KNOWLEDGE_DOCS  # noqa: E402


class FakeRagStore:
    """Deterministic test double: no model download or network dependency."""

    def __init__(self) -> None:
        self.ready = False

    def initialize(self) -> None:
        self.ready = True

    def retrieve(self, query: str, *, k: int = 3) -> list[RetrievedChunk]:
        q = query.lower()
        if "mars" in q or "interplanetary" in q:
            return []
        if "insur" in q:
            category = "insurance"
        elif "dealer" in q:  # before "financ" so "dealership financing" matches here
            category = "dealer-finance"
        elif "auction" in q:
            category = "auctions"
        elif "financ" in q or "eligible" in q:
            category = "financing"
        elif "trade" in q:
            category = "trade-in"
        else:
            category = "policies"
        docs = [d for d in KNOWLEDGE_DOCS if d["category"] == category][:k]
        return [
            RetrievedChunk(
                source_id=d["id"],
                title=d["title"],
                category=d["category"],
                text=d["text"],
                score=0.9,
                source_url=d.get("source_url"),
            )
            for d in docs
        ]


@pytest.fixture(scope="session")
def client() -> TestClient:
    app = create_app(
        llm_provider=FakeProvider(),
        rag_store=FakeRagStore(),
        allow_fake=True,
        eager_init=True,
    )
    return TestClient(app)


@pytest.fixture(scope="session")
def david_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={"username": "david", "password": "demo1234"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture
def auth(david_token: str) -> dict:
    return {"Authorization": f"Bearer {david_token}"}
