"""Listing confirmation — the only place a user-created listing is persisted.

Mirrors the bid confirm gate: verify the signed draft, enforce ownership from the
server-verified JWT (never the request body), then insert idempotently guarded by the
UNIQUE source_draft_id. A duplicate confirm returns the existing receipt (created=false).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import listingsign
from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import UsedCarDTO, UserDTO
from ..db.engine import get_session

router = APIRouter(prefix="/api", tags=["listings"])

class ConfirmListingRequest(BaseModel):
    signed_draft: dict
    session_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmListingResponse(BaseModel):
    listing: UsedCarDTO
    created: bool


class CancelListingRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/listings/confirm", response_model=ConfirmListingResponse)
def confirm_listing(
    body: ConfirmListingRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> ConfirmListingResponse:
    settings = request.app.state.settings
    sessions = request.app.state.sessions
    sid = sessions.scoped_id(user.id, body.session_id)

    # 1) signature + expiry
    try:
        draft = listingsign.verify_signed_draft(settings.bid_signing_secret, body.signed_draft)
    except listingsign.DraftError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid listing draft: {exc}")

    # 2) ownership from the verified JWT, never the request body
    if draft.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Draft does not belong to you")

    # 3) already persisted? return the existing receipt without needing the Redis draft
    existing = repo.get_listing_by_draft_id(db, draft.draft_id)
    if existing:
        sessions.clear_listing_draft(sid)
        return ConfirmListingResponse(listing=existing, created=False)

    # 4) otherwise require a matching, ready, user-scoped Redis draft
    stored = sessions.get_listing_draft(sid)
    if not stored or stored.get("status") != "ready" or stored.get("draft_id") != draft.draft_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No matching listing draft to confirm")
    stored_fields = stored.get("fields", {})
    if any(stored_fields.get(f) != draft.fields.get(f) for f in listingsign.LISTING_FIELDS):
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft fields do not match")

    # 5) idempotent insert (unique source_draft_id), then clear the draft
    listing, created = repo.create_listing(
        db, owner_id=user.id, draft_id=draft.draft_id, fields=draft.fields
    )
    sessions.clear_listing_draft(sid)
    return ConfirmListingResponse(listing=listing, created=created)


@router.post("/listings/cancel")
def cancel_listing(
    body: CancelListingRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
) -> dict:
    sessions = request.app.state.sessions
    sessions.clear_listing_draft(sessions.scoped_id(user.id, body.session_id))
    return {"ok": True}


@router.get("/listings", response_model=list[UsedCarDTO])
def my_listings(
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[UsedCarDTO]:
    return repo.list_user_listings(db, user.id)
