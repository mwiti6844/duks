"""Runtime dependencies handed to graph nodes (DB, RAG, LLM, session memory, settings)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import Settings
from ..llm.provider import LLMProvider
from ..memory.session import SessionStore
from ..rag.store import RagStore


@dataclass
class Deps:
    db_factory: Callable[[], Session]
    rag: RagStore
    llm: LLMProvider
    sessions: SessionStore
    settings: Settings
