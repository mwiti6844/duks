"""Deterministic tools. Authorization and ALL financial rules live here — never in
prompts. Tools return plain domain dicts; the SSE adapter turns them into UI events.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import bidsign
from ..db import repositories as repo
from ..db.dto import AuctionDTO, UsedCarDTO


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

# ── Financing rules (NCBA-style demo defaults) ──
DEFAULT_ANNUAL_RATE_PCT = 14.0
DEFAULT_DEPOSIT_PCT = 0.20
DEFAULT_TERM_MONTHS = 48
MIN_DEPOSIT_PCT = 0.20


def car_to_props(car: UsedCarDTO) -> dict:
    return {
        "id": car.id,
        "make": car.make,
        "model": car.model,
        "year": car.year,
        "price_kes": car.price_kes,
        "mileage_km": car.mileage_km,
        "transmission": car.transmission,
        "fuel": car.fuel,
        "location": car.location,
        "condition": car.condition,
        "body_type": car.body_type,
        "image_url": car.image_url,
        "description": car.description,
    }


def auction_to_props(auction: AuctionDTO) -> dict:
    return {
        "id": auction.id,
        "make": auction.make,
        "model": auction.model,
        "year": auction.year,
        "mileage_km": auction.mileage_km,
        "transmission": auction.transmission,
        "location": auction.location,
        "image_url": auction.image_url,
        "current_bid_kes": auction.current_bid_kes,
        "min_increment_kes": auction.min_increment_kes,
        "min_next_bid_kes": auction.current_bid_kes + auction.min_increment_kes,
        "ends_at": _as_utc(auction.ends_at).isoformat(),
    }


# ── Discovery ──
def search_cars(
    db: Session,
    *,
    make: str | None,
    model: str | None,
    max_price_kes: int | None,
    min_price_kes: int | None,
) -> list[UsedCarDTO]:
    return repo.search_used_cars(
        db,
        make=make,
        model=model,
        max_price_kes=max_price_kes,
        min_price_kes=min_price_kes,
    )


def compare_cars(db: Session, car_ids: list[str]) -> list[UsedCarDTO]:
    cars = [repo.get_used_car(db, cid) for cid in car_ids]
    return [c for c in cars if c is not None]


def price_verdict(db: Session, car: UsedCarDTO) -> dict:
    """Deterministic verdict over SOLD comparables. Evidence = sold listing ids."""
    comps = repo.comparable_sales(db, make=car.make, model=car.model)
    sold_prices = [c.sold_price_kes for c in comps if c.sold_price_kes]
    if not sold_prices:
        return {
            "verdict": "insufficient_data",
            "car_id": car.id,
            "asking_price_kes": car.price_kes,
            "evidence": [],
            "summary": "Not enough recent comparable sales to assess this price.",
        }
    median = int(statistics.median(sold_prices))
    low, high = min(sold_prices), max(sold_prices)
    delta_pct = round((car.price_kes - median) / median * 100, 1)
    if delta_pct <= -5:
        verdict = "below_market"
    elif delta_pct >= 8:
        verdict = "above_market"
    else:
        verdict = "fair"
    return {
        "verdict": verdict,
        "car_id": car.id,
        "asking_price_kes": car.price_kes,
        "comparable_median_kes": median,
        "comparable_low_kes": low,
        "comparable_high_kes": high,
        "delta_pct": delta_pct,
        "evidence": [
            {"sale_id": c.id, "sold_price_kes": c.sold_price_kes, "year": c.year, "mileage_km": c.mileage_km}
            for c in comps
        ],
    }


# ── Financing (deterministic amortization) ──
def compute_financing(
    *,
    principal_kes: int,
    deposit_kes: int | None = None,
    term_months: int = DEFAULT_TERM_MONTHS,
    annual_rate_pct: float = DEFAULT_ANNUAL_RATE_PCT,
) -> dict:
    if deposit_kes is None:
        deposit_kes = int(principal_kes * DEFAULT_DEPOSIT_PCT)
    deposit_kes = max(0, min(deposit_kes, principal_kes))
    financed = principal_kes - deposit_kes
    monthly_rate = annual_rate_pct / 100 / 12
    if monthly_rate == 0:
        monthly = financed / term_months if term_months else financed
    else:
        monthly = (
            financed * monthly_rate * (1 + monthly_rate) ** term_months
        ) / ((1 + monthly_rate) ** term_months - 1)
    total_payable = monthly * term_months + deposit_kes
    meets_min_deposit = deposit_kes >= principal_kes * MIN_DEPOSIT_PCT
    return {
        "price_kes": principal_kes,
        "deposit_kes": deposit_kes,
        "deposit_pct": round(deposit_kes / principal_kes * 100, 1) if principal_kes else 0,
        "financed_kes": financed,
        "term_months": term_months,
        "annual_rate_pct": annual_rate_pct,
        "monthly_payment_kes": int(round(monthly)),
        "total_payable_kes": int(round(total_payable)),
        "meets_min_deposit": meets_min_deposit,
        "min_deposit_kes": int(principal_kes * MIN_DEPOSIT_PCT),
    }


# ── Bidding (authz + financial rules + signed proposal) ──
class BidRuleError(Exception):
    pass


def validate_bid_rules(auction: AuctionDTO, amount_kes: int) -> None:
    """Re-run mutable auction rules immediately before proposal and confirmation."""
    min_next = auction.current_bid_kes + auction.min_increment_kes
    if amount_kes < min_next:
        raise BidRuleError(
            f"Bid must be at least KES {min_next:,} "
            f"(current bid + minimum increment)."
        )
    if _as_utc(auction.ends_at) <= datetime.now(timezone.utc):
        raise BidRuleError("This auction has already ended.")


def prepare_bid_proposal(
    db: Session,
    *,
    secret: str,
    user_id: str,
    auction: AuctionDTO,
    amount_kes: int,
) -> dict:
    """Validate a bid against the auction's financial rules, then create a signed,
    expiring proposal. Does NOT persist anything — only POST /api/bids/confirm does.
    """
    validate_bid_rules(auction, amount_kes)

    proposal = bidsign.create_proposal(
        user_id=user_id, auction_id=auction.id, amount_kes=amount_kes
    )
    signed = bidsign.make_signed_proposal(secret, proposal)
    return {
        "signed_proposal": signed,
        "auction": auction_to_props(auction),
        "amount_kes": amount_kes,
        "meets_reserve": amount_kes >= auction.reserve_price_kes,
    }
