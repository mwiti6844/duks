from __future__ import annotations

from app.db import repositories as repo
from app.db.engine import SessionLocal
from app.llm.provider import FakeProvider
from app.thread_titles import refresh_thread_title


def test_semantic_fallback_uses_structured_thread_context(client):
    with SessionLocal() as db:
        thread = repo.create_conversation_thread(db, user_id="usr_david")
        repo.append_conversation_message(
            db,
            thread_id=thread.id,
            user_id="usr_david",
            role="user",
            content=[{"type": "text", "text": "Something affordable please"}],
        )
        repo.update_conversation_thread(
            db,
            thread_id=thread.id,
            user_id="usr_david",
            context={
                "last_intent": "discovery.search",
                "search_constraints": {
                    "min_price_kes": 900_000,
                    "max_price_kes": 2_000_000,
                },
            },
        )

    refresh_thread_title(thread.id, "usr_david", FakeProvider())
    with SessionLocal() as db:
        updated = repo.get_conversation_thread(
            db, thread_id=thread.id, user_id="usr_david"
        )
        assert updated.title == "Car search · KES 900K–2M"


def test_manual_title_lock_prevents_automatic_overwrite(client):
    with SessionLocal() as db:
        thread = repo.create_conversation_thread(
            db, user_id="usr_david", title="My shortlist"
        )
        repo.append_conversation_message(
            db,
            thread_id=thread.id,
            user_id="usr_david",
            role="user",
            content=[{"type": "text", "text": "Find a Subaru Forester"}],
        )
        repo.update_conversation_thread(
            db,
            thread_id=thread.id,
            user_id="usr_david",
            context={
                "last_intent": "discovery.search",
                "search_constraints": {"make": "Subaru", "model": "Forester"},
            },
        )

    refresh_thread_title(thread.id, "usr_david", FakeProvider())
    with SessionLocal() as db:
        unchanged = repo.get_conversation_thread(
            db, thread_id=thread.id, user_id="usr_david"
        )
        assert unchanged.title == "My shortlist"
        assert unchanged.title_locked is True
