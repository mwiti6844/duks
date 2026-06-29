"""Readiness flag flipped true only after DB seeding + ChromaDB embedding complete.

Background init lets /api/health answer 503 'starting' immediately and flip to
'ready' when done (a blocking lifespan would make the endpoint unanswerable).
"""
from __future__ import annotations

import threading


class Readiness:
    def __init__(self) -> None:
        self._ready = threading.Event()
        self._error: str | None = None

    def mark_ready(self) -> None:
        self._ready.set()

    def mark_error(self, message: str) -> None:
        self._error = message

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    @property
    def error(self) -> str | None:
        return self._error

    def status(self) -> dict:
        if self._error:
            return {"status": "error", "detail": self._error}
        return {"status": "ready" if self.is_ready else "starting"}
