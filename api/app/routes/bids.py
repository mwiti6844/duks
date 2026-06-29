"""Bid confirmation — the only place a bid is persisted.

Redis and SQLite can't share one transaction, so confirmation is idempotent on
proposal_id: verify signature+expiry -> verify user/auction/amount -> insert in a SQL
transaction guarded by the UNIQUE proposal_id constraint -> clear the Redis pending
proposal. A duplicate proposal_id returns the existing receipt (no second bid).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import bidsign
from ..agents import tools
from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import BidDTO, UserDTO
from ..db.engine import get_session

router = APIRouter(prefix="/api", tags=["bids"])


class ConfirmBidRequest(BaseModel):
    signed_proposal: dict
    session_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmBidResponse(BaseModel):
    bid: BidDTO
    created: bool
    meets_reserve: bool


@router.post("/bids/confirm", response_model=ConfirmBidResponse)
def confirm_bid(
    body: ConfirmBidRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> ConfirmBidResponse:
    settings = request.app.state.settings
    try:
        proposal = bidsign.verify_signed_proposal(settings.bid_signing_secret, body.signed_proposal)
    except bidsign.ProposalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid bid proposal: {exc}")

    # Authorization: a user may only confirm their own proposal.
    if proposal.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Proposal does not belong to you")

    auction = repo.get_auction(db, proposal.auction_id)
    if auction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auction not found")

    # Idempotent retries remain successful even after the pending Redis entry was
    # consumed or the auction's high bid moved.
    existing = repo.get_bid_by_proposal(db, proposal.proposal_id)
    if existing is not None:
        if (
            existing.user_id != user.id
            or existing.auction_id != proposal.auction_id
            or existing.amount_kes != proposal.amount_kes
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposal conflicts with an existing bid")
        return ConfirmBidResponse(
            bid=existing,
            created=False,
            meets_reserve=proposal.amount_kes >= auction.reserve_price_kes,
        )

    sessions = request.app.state.sessions
    sid = sessions.scoped_id(user.id, body.session_id)
    pending = sessions.get_pending_bid(sid)
    if pending is None or pending.get("signed_proposal") != body.signed_proposal:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This proposal is not the pending bid for your session",
        )

    try:
        tools.validate_bid_rules(auction, proposal.amount_kes)
    except tools.BidRuleError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    bid, created = repo.confirm_bid(
        db,
        proposal_id=proposal.proposal_id,
        user_id=proposal.user_id,
        auction_id=proposal.auction_id,
        amount_kes=proposal.amount_kes,
    )
    # Clear the pending proposal so a later refresh won't re-offer it.
    sessions.clear_pending_bid(sid)
    return ConfirmBidResponse(
        bid=bid,
        created=created,
        meets_reserve=proposal.amount_kes >= auction.reserve_price_kes,
    )


class CancelBidRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/bids/cancel")
def cancel_pending_bid(
    body: CancelBidRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
) -> dict:
    sessions = request.app.state.sessions
    sessions.clear_pending_bid(sessions.scoped_id(user.id, body.session_id))
    return {"ok": True}


@router.get("/bids", response_model=list[BidDTO])
def my_bids(
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[BidDTO]:
    return repo.list_user_bids(db, user.id)
