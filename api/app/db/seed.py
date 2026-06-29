"""Idempotent DB seeding. Refreshes auction end times on every boot so countdowns
never expire mid-demo, and (re)hashes the two demo users."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..seed_data import auctions as auctions_seed
from ..seed_data import cars as cars_seed
from ..seed_data import real_cars as real_cars_seed
from ..seed_data import users as users_seed
from . import models

# Demo auctions whose ends_at we refresh on every boot if they're in the past.
_AUCTION_REFRESH_WINDOW = timedelta(hours=1)


def hash_password(raw: str) -> str:
    # bcrypt operates on <=72 bytes; truncate defensively.
    digest = bcrypt.hashpw(raw.encode()[:72], bcrypt.gensalt())
    return digest.decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def seed_users(db: Session) -> None:
    for u in users_seed.USERS:
        if db.get(models.User, u["id"]):
            continue
        db.add(
            models.User(
                id=u["id"],
                username=u["username"],
                full_name=u["full_name"],
                location=u["location"],
                profile_context=u.get("profile_context"),
                password_hash=hash_password(u["password"]),
            )
        )
    db.commit()


def _insert_car_if_absent(db: Session, row: dict, *, status: str, sold_at: datetime | None = None) -> None:
    """Per-row idempotency: insert by primary-key id only if absent, so seeding the
    curated + real rows works against an already-seeded database."""
    if db.get(models.UsedCarListing, row["id"]):
        return
    data = {"fuel": "Petrol", "status": status, **row}  # row's own fuel wins if present
    if sold_at is not None:
        data["sold_at"] = sold_at
    db.add(models.UsedCarListing(**data))


def seed_cars(db: Session) -> None:
    # Active: curated hero rows (need image + fuel default) then the real scraped rows.
    for r in cars_seed.with_images(cars_seed.ACTIVE_CARS):
        _insert_car_if_absent(db, dict(r), status="active")
    for r in real_cars_seed.REAL_ACTIVE:
        _insert_car_if_absent(db, dict(r), status="active")
    # Sold comparables (curated + simulated-from-real); sold_at is relative to now.
    for r in list(cars_seed.with_images(cars_seed.SOLD_CARS)) + list(real_cars_seed.REAL_SOLD):
        row = dict(r)
        days = row.pop("sold_days_ago")
        _insert_car_if_absent(db, row, status="sold", sold_at=_utcnow() - timedelta(days=days))
    db.commit()


def seed_auctions(db: Session) -> None:
    """Insert auctions if absent; always refresh ends_at relative to now so the
    demo never shows an expired countdown."""
    now = _utcnow()
    existing_ids = set(db.scalars(select(models.AuctionListing.id)).all())
    for r in auctions_seed.with_images(auctions_seed.AUCTIONS):
        row = {**r}
        ends_at = now + timedelta(hours=row.pop("ends_hours_from_now"))
        if row["id"] in existing_ids:
            auction = db.get(models.AuctionListing, row["id"])
            if auction:
                current = auction.ends_at
                if current.tzinfo is None:
                    current = current.replace(tzinfo=timezone.utc)
                if current <= now + _AUCTION_REFRESH_WINDOW:
                    auction.ends_at = ends_at
            continue
        db.add(models.AuctionListing(ends_at=ends_at, **row))
    db.commit()


def seed_all(db: Session) -> None:
    seed_users(db)
    seed_cars(db)
    seed_auctions(db)
