"""Session memory backed by Redis with an in-memory fallback.

Stores per-session:
  - conversation history (for /api/session/bootstrap restore)
  - displayed_used_car_ids / displayed_auction_ids / focused_listing_id
    (so ordinal references like "compare the first two" resolve deterministically)
  - the pending signed bid proposal (so a page refresh can restore the modal)
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

_HISTORY_KEY = "carduka:session:{sid}:history"
_TURNS_KEY = "carduka:session:{sid}:turns"
_STATE_KEY = "carduka:session:{sid}:state"
_PENDING_BID_KEY = "carduka:session:{sid}:pending_bid"
_LAST_RESULT_KEY = "carduka:session:{sid}:last_result"
_LISTING_DRAFT_KEY = "carduka:session:{sid}:listing_draft"
_TTL_SECONDS = 60 * 60 * 6  # 6h — comfortably longer than any demo


class _InMemoryBackend:
    """Process-local dict store mirroring the subset of Redis ops we use."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self.lock = threading.RLock()

    def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at and expires_at < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: int) -> None:
        self._data[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


def _default_context() -> dict:
    return {
        "version": 1,
        "active_journey": None,
        "last_intent": None,
        "displayed_used_car_ids": [],
        "displayed_auction_ids": [],
        "focused_entity_type": None,
        "focused_entity_id": None,
        # Backward-compatible alias used by existing agents.
        "focused_listing_id": None,
        "selected_car_ids": [],
        "comparison_car_ids": [],
        "comparison_anchor_id": None,
        "search_constraints": {},
        "awaiting_buy_criteria": False,
        "buy_intake_step": None,
        "listing_draft_paused": False,
        "conversation_summary": "",
    }


class SessionStore:
    def __init__(self, redis_url: str | None, *, allow_fallback: bool = True) -> None:
        self._backend: Any
        self._label: str
        if redis_url:
            try:
                import redis

                client = redis.Redis.from_url(redis_url, decode_responses=True)
                client.ping()
                self._backend = client
                self._label = "redis"
            except Exception as exc:
                if not allow_fallback:
                    raise RuntimeError("Redis is required but unavailable") from exc
                self._backend = _InMemoryBackend()
                self._label = "memory(redis-unreachable)"
        else:
            if not allow_fallback:
                raise RuntimeError("REDIS_URL is required in this environment")
            self._backend = _InMemoryBackend()
            self._label = "memory"

    @property
    def label(self) -> str:
        return self._label

    @staticmethod
    def scoped_id(user_id: str, session_id: str) -> str:
        """Bind every browser-provided session id to the authenticated user."""
        return f"{user_id}:{session_id}"

    def _get(self, key: str) -> str | None:
        return self._backend.get(key)

    def _set(self, key: str, value: str) -> None:
        # redis.set signature differs from the fallback; normalise.
        if self._label.startswith("redis"):
            self._backend.set(key, value, ex=_TTL_SECONDS)
        else:
            self._backend.set(key, value, _TTL_SECONDS)

    def _delete(self, key: str) -> None:
        self._backend.delete(key)

    def _update_json(
        self, key: str, default_factory: Callable[[], Any], mutate: Callable[[Any], Any]
    ) -> Any:
        """Atomically read/modify/write JSON for concurrent chat requests."""
        if self._label == "redis":
            import redis

            while True:
                try:
                    with self._backend.pipeline() as pipe:
                        pipe.watch(key)
                        raw = pipe.get(key)
                        value = json.loads(raw) if raw else default_factory()
                        updated = mutate(value)
                        pipe.multi()
                        pipe.set(key, json.dumps(updated), ex=_TTL_SECONDS)
                        pipe.execute()
                        return updated
                except redis.WatchError:
                    continue

        with self._backend.lock:
            raw = self._get(key)
            value = json.loads(raw) if raw else default_factory()
            updated = mutate(value)
            self._set(key, json.dumps(updated))
            return updated

    # ── conversation history ──
    def get_history(self, sid: str) -> list[dict]:
        raw = self._get(_HISTORY_KEY.format(sid=sid))
        return json.loads(raw) if raw else []

    def append_history(self, sid: str, role: str, content: str) -> None:
        def append(history: list[dict]) -> list[dict]:
            return [*history, {"role": role, "content": content}][-30:]

        self._update_json(_HISTORY_KEY.format(sid=sid), list, append)

    def get_turns(self, sid: str) -> list[dict]:
        raw = self._get(_TURNS_KEY.format(sid=sid))
        return json.loads(raw) if raw else []

    def append_turn(
        self, sid: str, *, turn_id: str, role: str, text: str, components: list[dict]
    ) -> None:
        turn = {
            "id": turn_id,
            "role": role,
            "text": text,
            "components": components,
            "created_at": int(time.time()),
        }

        def append(turns: list[dict]) -> list[dict]:
            return [*turns, turn][-24:]

        self._update_json(_TURNS_KEY.format(sid=sid), list, append)

    def ensure_turns_from_history(self, sid: str) -> None:
        """One-time migration for sessions created before structured turns existed."""
        if self.get_turns(sid):
            return
        history = self.get_history(sid)
        if not history:
            return
        migrated = [
            {
                "id": f"legacy_{index}",
                "role": item.get("role", "assistant"),
                "text": item.get("content", ""),
                "components": [],
                "created_at": 0,
            }
            for index, item in enumerate(history[-24:])
        ]

        def initialize(existing: list[dict]) -> list[dict]:
            return existing or migrated

        self._update_json(_TURNS_KEY.format(sid=sid), list, initialize)

    # ── structured conversation context ──
    def get_state(self, sid: str) -> dict:
        raw = self._get(_STATE_KEY.format(sid=sid))
        return _default_context() | (json.loads(raw) if raw else {})

    def update_state(self, sid: str, **changes: Any) -> dict:
        def update(state: dict) -> dict:
            merged = _default_context() | state
            merged.update(changes)
            return merged

        return self._update_json(_STATE_KEY.format(sid=sid), _default_context, update)

    def refresh_summary(self, sid: str) -> str:
        """Keep a compact recent-turn digest for prompt context after raw turns roll off."""
        turns = self.get_history(sid)[-8:]
        summary = "\n".join(
            f"{item.get('role', 'unknown')}: {item.get('content', '')[:300]}" for item in turns
        )[-2_000:]
        self.update_state(sid, conversation_summary=summary)
        return summary

    # ── pending bid proposal ──
    def set_pending_bid(self, sid: str, proposal: dict) -> None:
        self._set(_PENDING_BID_KEY.format(sid=sid), json.dumps(proposal))

    def get_pending_bid(self, sid: str) -> dict | None:
        raw = self._get(_PENDING_BID_KEY.format(sid=sid))
        return json.loads(raw) if raw else None

    def clear_pending_bid(self, sid: str) -> None:
        self._delete(_PENDING_BID_KEY.format(sid=sid))

    # ── completed turn result ──
    def set_last_result(self, sid: str, result: dict) -> None:
        self._set(_LAST_RESULT_KEY.format(sid=sid), json.dumps(result))

    def get_last_result(self, sid: str) -> dict | None:
        raw = self._get(_LAST_RESULT_KEY.format(sid=sid))
        return json.loads(raw) if raw else None

    # ── listing draft (multi-turn sell flow; user-scoped via the sid) ──
    def get_listing_draft(self, sid: str) -> dict | None:
        raw = self._get(_LISTING_DRAFT_KEY.format(sid=sid))
        return json.loads(raw) if raw else None

    def save_listing_draft(self, sid: str, draft: dict) -> None:
        self._set(_LISTING_DRAFT_KEY.format(sid=sid), json.dumps(draft))

    def clear_listing_draft(self, sid: str) -> None:
        self._delete(_LISTING_DRAFT_KEY.format(sid=sid))
