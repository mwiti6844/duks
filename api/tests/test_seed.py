from __future__ import annotations

from sqlalchemy import func, select

from app.db.engine import SessionLocal
from app.db.models import UsedCarListing
from app.db.seed import seed_all


def _count(db) -> int:
    return db.scalar(select(func.count()).select_from(UsedCarListing))


def test_seed_is_per_row_idempotent_and_augments(client):
    """Re-seeding over an already-seeded DB must not duplicate rows, and the DB must
    contain BOTH curated hero rows and real scraped rows."""
    with SessionLocal() as db:
        before = _count(db)
        # Curated hero row (demo/tests depend on it) and a real scraped row both present.
        assert db.get(UsedCarListing, "car_for_01") is not None  # Subaru Forester (curated)
        assert db.get(UsedCarListing, "car_real_01") is not None  # real scraped listing
        # Seeding again is a no-op (per-row idempotency by id).
        seed_all(db)
        seed_all(db)
        after = _count(db)
        assert after == before


def test_sold_comparables_present(client):
    with SessionLocal() as db:
        sold = db.scalars(
            select(UsedCarListing.id).where(UsedCarListing.status == "sold")
        ).all()
        assert any(i.startswith("car_for_") for i in sold)  # curated Forester comps
        assert any(i.startswith("car_real_") for i in sold)  # simulated-from-real comps
