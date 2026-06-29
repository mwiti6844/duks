"""GET /api/session/bootstrap — restore conversation history and any pending bid
proposal after a page refresh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import UserDTO
from ..db.engine import get_session

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/bootstrap")
def bootstrap(
    request: Request,
    session_id: str = Query(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    sessions = request.app.state.sessions
    sid = sessions.scoped_id(user.id, session_id)
    return {
        "user": user.model_dump(),
        "history": sessions.get_history(sid),
        "turns": sessions.get_turns(sid),
        "pending_bid": sessions.get_pending_bid(sid),
        "display_state": sessions.get_state(sid),
        "conversation_context": sessions.get_state(sid),
        "user_memory": repo.get_user_memory(db, user.id).model_dump(),
        "last_result": sessions.get_last_result(sid),
        # Resume an unfinished sell flow: surface a ready draft's listing_summary, or a
        # plain flag the UI can use to prompt the seller to continue.
        "listing_draft": sessions.get_listing_draft(sid),
    }
