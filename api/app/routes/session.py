"""GET /api/session/bootstrap — restore conversation history and any pending bid
proposal after a page refresh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from .. import listingsign
from ..db import repositories as repo
from ..db.dto import UserDTO
from ..db.engine import get_session
from ..listing_validation import completion

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
    # One-time compatibility migration: turn an existing Redis-only conversation
    # into a durable thread without regenerating its interactive components.
    legacy_turns = sessions.get_turns(sid)
    durable_thread = repo.get_conversation_thread(
        db, thread_id=session_id, user_id=user.id
    )
    if durable_thread is None and legacy_turns:
        try:
            durable_thread = repo.ensure_conversation_thread(
                db, user_id=user.id, thread_id=session_id
            )
        except PermissionError:
            durable_thread = repo.create_conversation_thread(db, user_id=user.id)
        for turn in legacy_turns:
            blocks: list[dict] = []
            if turn.get("text"):
                blocks.append({"type": "text", "text": turn["text"]})
            for component in turn.get("components", []):
                blocks.append({
                    "type": "component",
                    "component_type": component.get("type"),
                    "schema_version": 1,
                    "props": component.get("props", {}),
                })
            if blocks:
                repo.append_conversation_message(
                    db,
                    thread_id=durable_thread.id,
                    user_id=user.id,
                    role=turn.get("role", "assistant"),
                    content=blocks,
                    message_id=f"{durable_thread.id}_{turn.get('id', 'legacy')}",
                )
    cached_draft = sessions.get_listing_draft(sid)
    durable = (
        repo.get_listing_draft(db, cached_draft["draft_id"], user.id)
        if cached_draft and cached_draft.get("draft_id")
        else repo.latest_listing_draft(db, user.id)
    )
    cached_draft = repo.listing_draft_payload(db, durable) if durable else None
    if cached_draft:
        sessions.save_listing_draft(sid, cached_draft)
    if cached_draft and cached_draft.get("status") == "ready_to_publish" \
            and not cached_draft.get("signed"):
        cached_draft["signed"] = listingsign.make_signed_draft(
            request.app.state.settings.bid_signing_secret,
            listingsign.create_draft(
                owner_id=user.id,
                fields=cached_draft["fields"],
                draft_id=cached_draft["draft_id"],
                revision=cached_draft["revision"],
                mode=cached_draft.get("mode", "create"),
                target_listing_id=cached_draft.get("target_listing_id"),
                image_ids=[image["id"] for image in cached_draft.get("images", [])],
            ),
        )
    if cached_draft:
        percent, missing = completion(cached_draft.get("fields", {}))
        cached_draft["progress"] = percent
        cached_draft["missing_fields"] = missing
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
        "listing_draft": cached_draft,
        "thread_id": durable_thread.id if durable_thread else None,
    }
