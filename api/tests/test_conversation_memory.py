from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import load_settings
from app.memory.session import SessionStore

from . import sse_helper as sse


def test_context_survives_bootstrap_and_tracks_journey(client, auth):
    sid = "sess-context-bootstrap"
    sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    response = client.get(
        "/api/session/bootstrap", headers=auth, params={"session_id": sid}
    )
    context = response.json()["conversation_context"]
    assert context["active_journey"] == "buying"
    assert context["last_intent"] == "discovery.search"
    assert context["focused_entity_type"] == "used_car"
    assert context["focused_entity_id"].startswith("car_")
    assert context["displayed_used_car_ids"]
    assert "Subaru Forester" in context["conversation_summary"]


def test_explicit_user_memory_is_durable_across_sessions(client, auth):
    sse.chat(
        client,
        auth,
        "My budget is 3M and I prefer Audi",
        "sess-memory-write",
    )
    response = client.get(
        "/api/session/bootstrap",
        headers=auth,
        params={"session_id": "sess-memory-read"},
    )
    memory = response.json()["user_memory"]
    assert memory["budget_kes"] == 3_000_000
    assert "Audi" in memory["preferred_makes"]


def test_atomic_in_memory_history_updates_do_not_lose_turns():
    store = SessionStore(None)
    sid = "usr:concurrent"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: store.append_history(sid, "user", f"turn-{i}"), range(30)))
    history = store.get_history(sid)
    assert len(history) == 30
    assert {item["content"] for item in history} == {f"turn-{i}" for i in range(30)}


def test_production_requires_redis(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("ALLOW_IN_MEMORY_SESSIONS", raising=False)
    settings = load_settings(allow_fake=True)
    assert settings.allow_in_memory_sessions is False
    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        SessionStore(settings.redis_url, allow_fallback=settings.allow_in_memory_sessions)
