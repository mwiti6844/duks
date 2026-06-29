"""Repository layer. All reads return immutable Pydantic DTOs; ORM stays internal."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .dto import AuctionDTO, BidDTO, FinancingDTO, UsedCarDTO, UserDTO, UserMemoryDTO


# ── Users ──
def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.scalar(select(models.User).where(models.User.username == username))


def get_user(db: Session, user_id: str) -> UserDTO | None:
    row = db.get(models.User, user_id)
    return UserDTO.model_validate(row) if row else None


def get_user_memory(db: Session, user_id: str) -> UserMemoryDTO:
    row = db.get(models.UserMemory, user_id)
    if row is None:
        return UserMemoryDTO(user_id=user_id)
    return UserMemoryDTO(
        user_id=user_id,
        budget_kes=row.budget_kes,
        preferred_makes=json.loads(row.preferred_makes_json or "[]"),
        preferred_body_types=json.loads(row.preferred_body_types_json or "[]"),
    )


def update_user_memory(
    db: Session,
    *,
    user_id: str,
    budget_kes: int | None = None,
    preferred_make: str | None = None,
    preferred_body_type: str | None = None,
) -> UserMemoryDTO:
    row = db.get(models.UserMemory, user_id)
    if row is None:
        row = models.UserMemory(user_id=user_id)
        db.add(row)
    if budget_kes is not None:
        row.budget_kes = budget_kes
    makes = json.loads(row.preferred_makes_json or "[]")
    body_types = json.loads(row.preferred_body_types_json or "[]")
    if preferred_make and preferred_make not in makes:
        makes.append(preferred_make)
    if preferred_body_type and preferred_body_type not in body_types:
        body_types.append(preferred_body_type)
    row.preferred_makes_json = json.dumps(makes[-10:])
    row.preferred_body_types_json = json.dumps(body_types[-10:])
    db.commit()
    return get_user_memory(db, user_id)


def distinct_vehicle_facets(db: Session) -> tuple[list[str], list[str]]:
    makes = list(db.scalars(select(models.UsedCarListing.make).distinct()).all())
    body_types = list(db.scalars(select(models.UsedCarListing.body_type).distinct()).all())
    return makes, body_types


# ── Used cars ──
def search_used_cars(
    db: Session,
    *,
    make: str | None = None,
    model: str | None = None,
    max_price_kes: int | None = None,
    min_price_kes: int | None = None,
    limit: int = 12,
) -> list[UsedCarDTO]:
    stmt = select(models.UsedCarListing).where(models.UsedCarListing.status == "active")
    if make:
        stmt = stmt.where(models.UsedCarListing.make.ilike(f"%{make}%"))
    if model:
        stmt = stmt.where(models.UsedCarListing.model.ilike(f"%{model}%"))
    if max_price_kes is not None:
        stmt = stmt.where(models.UsedCarListing.price_kes <= max_price_kes)
    if min_price_kes is not None:
        stmt = stmt.where(models.UsedCarListing.price_kes >= min_price_kes)
    stmt = stmt.order_by(models.UsedCarListing.price_kes.asc()).limit(limit)
    return [UsedCarDTO.model_validate(r) for r in db.scalars(stmt).all()]


def get_used_car(db: Session, car_id: str) -> UsedCarDTO | None:
    row = db.get(models.UsedCarListing, car_id)
    return UsedCarDTO.model_validate(row) if row else None


def comparable_sales(
    db: Session, *, make: str, model: str, limit: int = 6
) -> list[UsedCarDTO]:
    """Sold listings of the same make/model — evidence for the price verdict."""
    stmt = (
        select(models.UsedCarListing)
        .where(models.UsedCarListing.status == "sold")
        .where(models.UsedCarListing.make.ilike(f"%{make}%"))
        .where(models.UsedCarListing.model.ilike(f"%{model}%"))
        .order_by(models.UsedCarListing.sold_at.desc())
        .limit(limit)
    )
    return [UsedCarDTO.model_validate(r) for r in db.scalars(stmt).all()]


# ── Auctions ──
def list_auctions(db: Session, limit: int = 12) -> list[AuctionDTO]:
    stmt = select(models.AuctionListing).order_by(models.AuctionListing.ends_at.asc()).limit(limit)
    return [AuctionDTO.model_validate(r) for r in db.scalars(stmt).all()]


def get_auction(db: Session, auction_id: str) -> AuctionDTO | None:
    row = db.get(models.AuctionListing, auction_id)
    return AuctionDTO.model_validate(row) if row else None


def find_auction_by_model(db: Session, model: str) -> AuctionDTO | None:
    stmt = (
        select(models.AuctionListing)
        .where(models.AuctionListing.model.ilike(f"%{model}%"))
        .order_by(models.AuctionListing.ends_at.asc())
    )
    row = db.scalars(stmt).first()
    return AuctionDTO.model_validate(row) if row else None


# ── Bids (idempotent on proposal_id) ──
def get_bid_by_proposal(db: Session, proposal_id: str) -> BidDTO | None:
    row = db.scalar(select(models.Bid).where(models.Bid.proposal_id == proposal_id))
    return BidDTO.model_validate(row) if row else None


def confirm_bid(
    db: Session, *, proposal_id: str, user_id: str, auction_id: str, amount_kes: int
) -> tuple[BidDTO, bool]:
    """Persist exactly one bid per proposal_id.

    Returns (bid, created). On a duplicate proposal_id the existing receipt is
    returned with created=False (idempotent retry, no second bid).
    """
    existing = db.scalar(select(models.Bid).where(models.Bid.proposal_id == proposal_id))
    if existing:
        return BidDTO.model_validate(existing), False

    bid = models.Bid(
        id=f"bid_{uuid.uuid4().hex[:10]}",
        proposal_id=proposal_id,
        user_id=user_id,
        auction_id=auction_id,
        amount_kes=amount_kes,
    )
    db.add(bid)
    # Reflect the new high bid on the auction so the demo stays coherent.
    auction = db.get(models.AuctionListing, auction_id)
    if auction and amount_kes > auction.current_bid_kes:
        auction.current_bid_kes = amount_kes
    try:
        db.commit()
    except IntegrityError:
        # Concurrent insert won the unique constraint — return the winner's receipt.
        db.rollback()
        winner = db.scalar(select(models.Bid).where(models.Bid.proposal_id == proposal_id))
        return BidDTO.model_validate(winner), False
    db.refresh(bid)
    return BidDTO.model_validate(bid), True


def list_user_bids(db: Session, user_id: str) -> list[BidDTO]:
    stmt = (
        select(models.Bid)
        .where(models.Bid.user_id == user_id)
        .order_by(models.Bid.created_at.desc())
    )
    return [BidDTO.model_validate(r) for r in db.scalars(stmt).all()]


# ── Financing ──
def save_financing(
    db: Session,
    *,
    user_id: str,
    car_id: str,
    principal_kes: int,
    deposit_kes: int,
    term_months: int,
    annual_rate_pct: float,
    monthly_payment_kes: int,
    approved: bool,
) -> FinancingDTO:
    app = models.FinancingApplication(
        id=f"fin_{uuid.uuid4().hex[:10]}",
        user_id=user_id,
        car_id=car_id,
        principal_kes=principal_kes,
        deposit_kes=deposit_kes,
        term_months=term_months,
        annual_rate_pct=annual_rate_pct,
        monthly_payment_kes=monthly_payment_kes,
        approved=approved,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return FinancingDTO.model_validate(app)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Listings (user-created via the Listings agent) ──
def get_listing_by_draft_id(db: Session, draft_id: str) -> UsedCarDTO | None:
    row = db.scalar(
        select(models.UsedCarListing).where(models.UsedCarListing.source_draft_id == draft_id)
    )
    return UsedCarDTO.model_validate(row) if row else None


def list_user_listings(db: Session, owner_id: str) -> list[UsedCarDTO]:
    stmt = (
        select(models.UsedCarListing)
        .where(models.UsedCarListing.owner_id == owner_id)
        .order_by(models.UsedCarListing.id.desc())
    )
    return [UsedCarDTO.model_validate(r) for r in db.scalars(stmt).all()]


def create_listing(
    db: Session, *, owner_id: str, draft_id: str, fields: dict
) -> tuple[UsedCarDTO, bool]:
    """Persist exactly one listing per source_draft_id (idempotent on retry).

    Returns (listing, created). A duplicate draft_id returns the existing row with
    created=False — never raises.
    """
    existing = get_listing_by_draft_id(db, draft_id)
    if existing:
        return existing, False

    row = models.UsedCarListing(
        id=f"car_user_{uuid.uuid4().hex[:10]}",
        status="active",
        owner_id=owner_id,
        source_draft_id=draft_id,
        make=fields["make"],
        model=fields["model"],
        year=int(fields["year"]),
        price_kes=int(fields["price_kes"]),
        mileage_km=int(fields["mileage_km"]),
        transmission=fields["transmission"],
        fuel=fields["fuel"],
        location=fields["location"],
        condition=fields["condition"],
        body_type=fields["body_type"],
        image_url=fields.get("image_url", ""),
        description=fields.get("description"),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent insert won the unique source_draft_id — return the winner.
        db.rollback()
        winner = get_listing_by_draft_id(db, draft_id)
        if winner:
            return winner, False
        raise
    db.refresh(row)
    return UsedCarDTO.model_validate(row), True
