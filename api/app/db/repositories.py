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
    max_mileage_km: int | None = None,
    min_mileage_km: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    body_types: list[str] | None = None,
    transmission: str | None = None,
    fuel: str | None = None,
    location: str | None = None,
    sort_by: str | None = None,
    limit: int = 8,
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
    if max_mileage_km is not None:
        stmt = stmt.where(models.UsedCarListing.mileage_km <= max_mileage_km)
    if min_mileage_km is not None:
        stmt = stmt.where(models.UsedCarListing.mileage_km >= min_mileage_km)
    if min_year is not None:
        stmt = stmt.where(models.UsedCarListing.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(models.UsedCarListing.year <= max_year)
    if body_types:
        stmt = stmt.where(models.UsedCarListing.body_type.in_(body_types))
    if transmission:
        stmt = stmt.where(models.UsedCarListing.transmission.ilike(transmission))
    if fuel:
        stmt = stmt.where(models.UsedCarListing.fuel.ilike(fuel))
    if location:
        stmt = stmt.where(models.UsedCarListing.location.ilike(f"%{location}%"))
    order = {
        "mileage_asc": models.UsedCarListing.mileage_km.asc(),
        "year_desc": models.UsedCarListing.year.desc(),
        "price_asc": models.UsedCarListing.price_kes.asc(),
    }.get(sort_by, models.UsedCarListing.price_kes.asc())
    stmt = stmt.order_by(order, models.UsedCarListing.price_kes.asc()).limit(limit)
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


# ── Durable listing drafts / images / revision receipts ──
def get_listing_draft(db: Session, draft_id: str, owner_id: str):
    return db.scalar(select(models.ListingDraft).where(
        models.ListingDraft.id == draft_id,
        models.ListingDraft.owner_id == owner_id,
    ))


def latest_listing_draft(db: Session, owner_id: str):
    return db.scalar(
        select(models.ListingDraft)
        .where(
            models.ListingDraft.owner_id == owner_id,
            models.ListingDraft.status.in_(("collecting", "needs_review", "ready_to_publish")),
        )
        .order_by(models.ListingDraft.updated_at.desc())
    )


def save_listing_draft(
    db: Session, *, draft_id: str, owner_id: str, fields: dict,
    status: str, validation: list[dict], guidance: dict,
    mode: str = "create", target_listing_id: str | None = None,
    increment_revision: bool = False,
):
    row = get_listing_draft(db, draft_id, owner_id)
    if row is None:
        row = models.ListingDraft(
            id=draft_id, owner_id=owner_id, mode=mode,
            target_listing_id=target_listing_id,
        )
        db.add(row)
    elif increment_revision:
        row.revision += 1
    row.fields_json = json.dumps(fields)
    row.status = status
    row.validation_json = json.dumps(validation)
    row.guidance_json = json.dumps(guidance)
    db.commit()
    db.refresh(row)
    return row


def listing_draft_payload(db: Session, row) -> dict:
    images = list_listing_images(db, row.id, row.owner_id)
    return {
        "draft_id": row.id,
        "owner_id": row.owner_id,
        "mode": row.mode,
        "target_listing_id": row.target_listing_id,
        "status": row.status,
        "revision": row.revision,
        "fields": json.loads(row.fields_json or "{}"),
        "validation": json.loads(row.validation_json or "[]"),
        "guidance": json.loads(row.guidance_json or "{}"),
        "images": [listing_image_payload(image) for image in images],
    }


def list_listing_images(db: Session, draft_id: str, owner_id: str):
    return list(db.scalars(
        select(models.ListingImage)
        .where(models.ListingImage.draft_id == draft_id,
               models.ListingImage.owner_id == owner_id)
        .order_by(models.ListingImage.sort_order)
    ).all())


def listing_image_payload(row) -> dict:
    return {
        "id": row.id, "public_id": row.cloudinary_public_id,
        "secure_url": row.secure_url, "width": row.width, "height": row.height,
        "sort_order": row.sort_order,
    }


def add_listing_image(
    db: Session, *, owner_id: str, draft_id: str, public_id: str,
    secure_url: str, width: int | None, height: int | None,
):
    images = list_listing_images(db, draft_id, owner_id)
    row = models.ListingImage(
        id=f"img_{uuid.uuid4().hex}", owner_id=owner_id, draft_id=draft_id,
        cloudinary_public_id=public_id, secure_url=secure_url,
        width=width, height=height, sort_order=len(images),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_listing_image(db: Session, *, image_id: str, owner_id: str) -> bool:
    row = get_listing_image(db, image_id, owner_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def get_listing_image(db: Session, image_id: str, owner_id: str):
    return db.scalar(select(models.ListingImage).where(
        models.ListingImage.id == image_id,
        models.ListingImage.owner_id == owner_id,
    ))


def get_listing_mutation(db: Session, draft_id: str, revision: int):
    return db.scalar(select(models.ListingMutation).where(
        models.ListingMutation.draft_id == draft_id,
        models.ListingMutation.revision == revision,
    ))


def apply_listing_draft(db: Session, draft, *, image_ids: list[str]) -> tuple[UsedCarDTO, bool]:
    existing_mutation = get_listing_mutation(db, draft.id, draft.revision)
    if existing_mutation:
        listing = db.get(models.UsedCarListing, existing_mutation.listing_id)
        return UsedCarDTO.model_validate(listing), False

    fields = json.loads(draft.fields_json)
    if draft.mode == "edit":
        listing = db.scalar(select(models.UsedCarListing).where(
            models.UsedCarListing.id == draft.target_listing_id,
            models.UsedCarListing.owner_id == draft.owner_id,
        ))
        if listing is None:
            raise ValueError("Target listing not found")
        for key in (
            "make", "model", "year", "price_kes", "mileage_km", "transmission",
            "fuel", "location", "condition", "body_type", "description",
        ):
            setattr(listing, key, fields[key])
        listing.version += 1
        operation = "edit"
    else:
        listing = models.UsedCarListing(
            id=f"car_user_{uuid.uuid4().hex[:10]}",
            status="active",
            owner_id=draft.owner_id,
            source_draft_id=draft.id,
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
            image_url="",
            description=fields["description"],
            published_at=_utcnow(),
        )
        db.add(listing)
        operation = "create"
    db.flush()

    images = list(db.scalars(select(models.ListingImage).where(
        models.ListingImage.id.in_(image_ids),
        models.ListingImage.owner_id == draft.owner_id,
        models.ListingImage.draft_id == draft.id,
    )).all()) if image_ids else []
    for image in images:
        image.listing_id = listing.id
    if images:
        listing.image_url = sorted(images, key=lambda item: item.sort_order)[0].secure_url

    mutation = models.ListingMutation(
        id=f"lmut_{uuid.uuid4().hex}",
        draft_id=draft.id,
        revision=draft.revision,
        owner_id=draft.owner_id,
        listing_id=listing.id,
        operation=operation,
    )
    db.add(mutation)
    draft.status = "published"
    db.commit()
    db.refresh(listing)
    return UsedCarDTO.model_validate(listing), True
