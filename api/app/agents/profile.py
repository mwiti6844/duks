"""Profile Agent: personalized greeting + the user's bids/history."""
from __future__ import annotations

import time
from collections.abc import Callable

from ..db import repositories as repo
from ..prompts import load_prompt
from .deps import Deps
from .events import TextDelta, ToolCompleted, ToolStarted, Trace
from .state import GraphState

Emit = Callable[[object], None]


def handle_profile(state: GraphState, deps: Deps, emit: Emit) -> None:
    user_id = state["user_id"]
    emit(ToolStarted(name="load_profile", params={"user_id": user_id}))
    t0 = time.time()
    with deps.db_factory() as db:
        user = repo.get_user(db, user_id)
        bids = repo.list_user_bids(db, user_id)
        memory = repo.get_user_memory(db, user_id)
    emit(ToolCompleted(name="load_profile", ms=int((time.time() - t0) * 1000),
                       detail={"active_bids": len(bids)}))

    if user is None:
        emit(TextDelta(text="Welcome to CarDuka!"))
        return

    bid_summary = (f"{len(bids)} active bid(s)" if bids else "no active bids yet")
    system, version = load_prompt("profile.v1")
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": version}))
    context_line = f" Context: {user.profile_context}" if user.profile_context else ""
    memory_line = (
        f" Confirmed preferences: budget={memory.budget_kes}, "
        f"makes={memory.preferred_makes}, body_types={memory.preferred_body_types}."
    )
    ctx = (f"User: {user.full_name}, location: {user.location}. "
           f"They have {bid_summary}.{context_line}{memory_line}")
    for chunk in deps.llm.stream_text(system=system, user=ctx, max_tokens=250):
        emit(TextDelta(text=chunk))
