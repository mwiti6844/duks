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

    # 3) already applied? return the existing receipt without needing Redis.
    mutation = repo.get_listing_mutation(db, draft.draft_id, draft.revision)
    if mutation:
        existing = repo.get_used_car(db, mutation.listing_id)
        sessions.clear_listing_draft(sid)
        return ConfirmListingResponse(listing=existing, created=False)

    # 4) SQLite is authoritative; Redis is only the active-session cache.
    durable = repo.get_listing_draft(db, draft.draft_id, user.id)
    if durable is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No matching listing draft to confirm")
    stored = repo.listing_draft_payload(db, durable)
    if stored["status"] != "ready_to_publish":
        raise HTTPException(status.HTTP_409_CONFLICT, "Listing is not ready to publish")
    if stored["revision"] != draft.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "Listing draft has changed; review it again")
    if stored["mode"] != draft.mode or stored["target_listing_id"] != draft.target_listing_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft operation does not match")
    if any(stored["fields"].get(f) != draft.fields.get(f) for f in listingsign.LISTING_FIELDS):
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft fields do not match")
    if [image["id"] for image in stored["images"]] != list(draft.image_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft photos have changed")

    # 5) Apply create/edit exactly once for this draft revision.
    try:
        listing, created = repo.apply_listing_draft(
            db, durable, image_ids=list(draft.image_ids)
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    sessions.clear_listing_draft(sid)
    return ConfirmListingResponse(listing=listing, created=created)


@router.post("/listings/cancel")
def cancel_listing(
    body: CancelListingRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    sessions = request.app.state.sessions
    sid = sessions.scoped_id(user.id, body.session_id)
    cached = sessions.get_listing_draft(sid)
    durable = (
        repo.get_listing_draft(db, cached["draft_id"], user.id)
        if cached and cached.get("draft_id")
        else None
    )
    if durable:
        durable.status = "cancelled"
        db.commit()
    sessions.clear_listing_draft(sid)
    return {"ok": True}


@router.get("/listings", response_model=list[UsedCarDTO])
def my_listings(
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[UsedCarDTO]:
    return repo.list_user_listings(db, user.id)


@router.get("/listings/{listing_id}", response_model=UsedCarDTO)
def listing_detail(
    listing_id: str,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UsedCarDTO:
    listing = repo.get_used_car(db, listing_id)
    if listing is None or (listing.owner_id is not None and listing.owner_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return listing
