from __future__ import annotations

from sqlalchemy import func, select

from app.db.engine import SessionLocal
from app.db.models import UsedCarImage, UsedCarListing
from app.db.seed import seed_all


def _count(db) -> int:
    return db.scalar(select(func.count()).select_from(UsedCarListing))


def test_seed_is_per_row_idempotent_and_augments(client):
    """Re-seeding over an already-seeded DB must not duplicate rows. The catalog is
    real scraped listings only (every row carries full data)."""
    with SessionLocal() as db:
        before = _count(db)
        images_before = db.scalar(select(func.count()).select_from(UsedCarImage))
        # Real scraped listing present; synthetic filler rows are no longer seeded.
        assert db.get(UsedCarListing, "car_real_01") is not None
        assert db.get(UsedCarListing, "car_for_01") is None
        # Seeding again is a no-op (per-row idempotency by id).
        seed_all(db)
        seed_all(db)
        after = _count(db)
        assert after == before
        assert db.scalar(select(func.count()).select_from(UsedCarImage)) == images_before


def test_sold_comparables_present(client):
    with SessionLocal() as db:
        sold = db.scalars(
            select(UsedCarListing.id).where(UsedCarListing.status == "sold")
        ).all()
        assert sold
        assert all(i.startswith("car_real_") for i in sold)  # real sold comparables
