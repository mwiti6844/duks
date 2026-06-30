from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from app.llm.provider import FakeProvider


class BrokenRag:
    ready = False

    def initialize(self) -> None:
        self.ready = True

    def retrieve(self, query: str, *, k: int = 3) -> list:
        return []


def test_readiness_fails_when_rag_cannot_retrieve():
    app = create_app(
        llm_provider=FakeProvider(),
        rag_store=BrokenRag(),
        allow_fake=True,
        eager_init=True,
    )
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error"
