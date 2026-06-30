"""SQLAlchemy ORM models. Internal only — callers receive Pydantic DTOs (see dto.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String, default="Nairobi")
    # Persona context surfaced to the Profile Agent (budget, preference, what they sell).
    profile_context: Mapped[str | None] = mapped_column(String, nullable=True)


class UserMemory(Base):
    """Confirmed, durable preferences shared across a user's sessions."""
    __tablename__ = "user_memories"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    budget_kes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_makes_json: Mapped[str] = mapped_column(String, default="[]")
    preferred_body_types_json: Mapped[str] = mapped_column(String, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class UsedCarListing(Base):
    __tablename__ = "used_car_listings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    make: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    price_kes: Mapped[int] = mapped_column(Integer, index=True)
    mileage_km: Mapped[int] = mapped_column(Integer)
    transmission: Mapped[str] = mapped_column(String)  # "Automatic" | "Manual"
    fuel: Mapped[str] = mapped_column(String, default="Petrol")
    location: Mapped[str] = mapped_column(String)
    condition: Mapped[str] = mapped_column(String, default="Excellent")
    body_type: Mapped[str] = mapped_column(String, default="Station Wagon")
    image_url: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # status: "active" listings are for sale; "sold" rows feed the price verdict.
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    sold_price_kes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ownership for user-created listings (from the Listings agent). Filtered by user_id;
    # NULL for seeded rows. tenant_id is intentionally deferred to future dealership accounts.
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Idempotency for the confirm gate: one persisted listing per signed draft (multiple
    # NULLs allowed under SQLite UNIQUE; only non-null draft ids must be unique).
    source_draft_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ListingDraft(Base):
    """Durable source of truth for create/edit listing conversations."""
    __tablename__ = "listing_drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String, default="create")  # create | edit
    target_listing_id: Mapped[str | None] = mapped_column(
        ForeignKey("used_car_listings.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="collecting", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_json: Mapped[str] = mapped_column(Text, default="[]")
    guidance_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("listing_drafts.id"), nullable=True, index=True
    )
    listing_id: Mapped[str | None] = mapped_column(
        ForeignKey("used_car_listings.id"), nullable=True, index=True
    )
    cloudinary_public_id: Mapped[str] = mapped_column(String, unique=True)
    secure_url: Mapped[str] = mapped_column(String)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ListingMutation(Base):
    """Idempotency receipt for both create and edit confirmations."""
    __tablename__ = "listing_mutations"
    __table_args__ = (
        UniqueConstraint("draft_id", "revision", name="uq_listing_mutation_revision"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    listing_id: Mapped[str] = mapped_column(ForeignKey("used_car_listings.id"))
    operation: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuctionListing(Base):
    __tablename__ = "auction_listings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    make: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer)
    mileage_km: Mapped[int] = mapped_column(Integer)
    transmission: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    image_url: Mapped[str] = mapped_column(String, default="")
    reserve_price_kes: Mapped[int] = mapped_column(Integer)
    current_bid_kes: Mapped[int] = mapped_column(Integer)
    min_increment_kes: Mapped[int] = mapped_column(Integer)
    # Absolute UTC instant; (re)generated relative to startup so it never expires mid-demo.
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (UniqueConstraint("proposal_id", name="uq_bids_proposal_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Defence-in-depth against replay: one persisted bid per signed proposal.
    proposal_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    auction_id: Mapped[str] = mapped_column(ForeignKey("auction_listings.id"))
    amount_kes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TradeIn(Base):
    __tablename__ = "trade_ins"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    make: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    year: Mapped[int] = mapped_column(Integer)
    estimated_value_kes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FinancingApplication(Base):
    __tablename__ = "financing_applications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    car_id: Mapped[str] = mapped_column(String)
    principal_kes: Mapped[int] = mapped_column(Integer)
    deposit_kes: Mapped[int] = mapped_column(Integer)
    term_months: Mapped[int] = mapped_column(Integer)
    annual_rate_pct: Mapped[float] = mapped_column(Float)
    monthly_payment_kes: Mapped[int] = mapped_column(Integer)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
