"""Deterministic tools. Authorization and ALL financial rules live here — never in
prompts. Tools return plain domain dicts; the SSE adapter turns them into UI events.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import bidsign
from ..db import repositories as repo
from ..db.dto import AuctionDTO, UsedCarDTO
from ..llm.provider import LLMProvider


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

# ── Financing rules (NCBA-style demo defaults) ──
DEFAULT_ANNUAL_RATE_PCT = 14.0
DEFAULT_DEPOSIT_PCT = 0.20
DEFAULT_TERM_MONTHS = 48
MIN_DEPOSIT_PCT = 0.20


def car_to_props(car: UsedCarDTO, *, include_gallery: bool = False) -> dict:
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
        "trim": car.trim,
        "color": car.color,
        "engine_cc": car.engine_cc,
        "monthly_payment_kes": car.monthly_payment_kes,
        "finance_term_months": car.finance_term_months,
        "source_url": car.source_url,
        "image_urls": car.image_urls if include_gallery else car.image_urls[:1],
    }


VEHICLE_FACT_FIELDS = (
    "identity", "price", "finance", "mileage", "engine", "transmission",
    "fuel", "body", "color", "condition", "location", "seller",
    "listing_reference", "features", "description", "images",
)

_FACT_ALIASES = {
    "engine": ("cc", "engine", "motor", "capacity", "displacement"),
    "finance": ("monthly", "per month", "finance", "financing", "repayment"),
    "color": ("color", "colour", "paint"),
    "images": ("image", "images", "photo", "photos", "picture", "pictures", "gallery"),
    "seller": ("seller", "dealer", "owner", "who is selling"),
    "location": ("location", "where", "viewing", "address"),
    "features": (
        "feature", "features", "sunroof", "camera", "leather", "sensor",
        "cruise", "safety", "interior", "extras",
    ),
    "listing_reference": ("listing id", "source", "link", "carduka page"),
    "transmission": ("transmission", "gearbox", "automatic", "manual", "cvt"),
    "fuel": ("fuel", "petrol", "diesel", "hybrid", "electric"),
    "mileage": ("mileage", "odometer", "kilomet"),
    "price": ("price", "cost", "cash"),
    "body": ("body", "suv", "sedan", "hatchback", "pickup", "wagon"),
    "condition": ("condition", "accident", "maintained"),
    "identity": ("trim", "variant", "model", "year", "make"),
    "description": ("description", "tell me more", "details", "what about"),
}


def is_vehicle_fact_question(message: str) -> bool:
    text = message.lower()
    return any(alias in text for aliases in _FACT_ALIASES.values() for alias in aliases)


def select_vehicle_fact_fields(message: str, llm: LLMProvider) -> list[str]:
    """Let the model select from a strict catalog, then validate deterministically."""
    text = message.lower()
    fallback = [
        field for field, aliases in _FACT_ALIASES.items()
        if any(alias in text for alias in aliases)
    ]
    if not fallback:
        fallback = [
            "identity", "price", "mileage", "engine", "transmission", "fuel",
            "body", "color", "condition", "location", "features", "description",
            "images",
        ]
    try:
        result = llm.complete_json(
            system=(
                "VEHICLE_FACT_SELECTION\nSelect only the database fact groups needed "
                "to answer the user's question. Never invent a field. Return JSON "
                f'only: {{"fields":[...]}}. Allowed fields: {list(VEHICLE_FACT_FIELDS)}'
            ),
            user=message,
            max_tokens=120,
        )
        proposed = result.get("fields", [])
        validated = [field for field in proposed if field in VEHICLE_FACT_FIELDS]
        return list(dict.fromkeys(validated or fallback))
    except Exception:
        return list(dict.fromkeys(fallback))


def vehicle_facts(car: UsedCarDTO, fields: list[str]) -> dict:
    """Return allow-listed, database-backed facts—never arbitrary ORM columns."""
    all_facts = {
        "identity": {
            "year": car.year, "make": car.make, "model": car.model, "trim": car.trim,
        },
        "price": {"cash_price_kes": car.price_kes},
        "finance": {
            "monthly_payment_kes": car.monthly_payment_kes,
            "term_months": car.finance_term_months,
        },
        "mileage": {"mileage_km": car.mileage_km},
        "engine": {"engine_cc": car.engine_cc},
        "transmission": {"transmission": car.transmission},
        "fuel": {"fuel": car.fuel},
        "body": {"body_type": car.body_type},
        "color": {"color": car.color},
        "condition": {"condition": car.condition},
        "location": {
            "area": car.location, "location_detail": car.location_detail,
        },
        "seller": {"seller_display_name": car.seller_name},
        "listing_reference": {
            "source_listing_id": car.source_listing_id, "source_url": car.source_url,
        },
        "features": {"features": car.specs.get("features", [])},
        "description": {"description": car.description},
        "images": {"image_count": len(car.image_urls)},
    }
    selected = {}
    for field in fields:
        values = {
            key: value for key, value in all_facts[field].items()
            if value not in (None, "", [])
        }
        if values:
            selected[field] = values
    return selected


def vehicle_facts_context(car: UsedCarDTO, fields: list[str]) -> str:
    return json.dumps({
        "listing_id": car.id,
        "requested_fact_groups": fields,
        "facts": vehicle_facts(car, fields),
    }, ensure_ascii=False)


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
    max_mileage_km: int | None = None,
    min_mileage_km: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    body_types: list[str] | None = None,
    transmission: str | None = None,
    fuel: str | None = None,
    location: str | None = None,
    sort_by: str | None = None,
) -> list[UsedCarDTO]:
    return repo.search_used_cars(
        db,
        make=make,
        model=model,
        max_price_kes=max_price_kes,
        min_price_kes=min_price_kes,
        max_mileage_km=max_mileage_km,
        min_mileage_km=min_mileage_km,
        min_year=min_year,
        max_year=max_year,
        body_types=body_types,
        transmission=transmission,
        fuel=fuel,
        location=location,
        sort_by=sort_by,
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
