"""Advisory seller price guidance derived only from sold-comparable database rows."""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from .db import repositories as repo


def price_guidance(db: Session, fields: dict) -> dict:
    make, model = fields.get("make"), fields.get("model")
    if not make or not model:
        return {"status": "insufficient_data", "evidence": []}
    comps = repo.comparable_sales(db, make=make, model=model)
    evidence = [
        {
            "sale_id": item.id,
            "year": item.year,
            "mileage_km": item.mileage_km,
            "sold_price_kes": item.sold_price_kes,
        }
        for item in comps if item.sold_price_kes
    ]
    prices = [item["sold_price_kes"] for item in evidence]
    if not prices:
        return {"status": "insufficient_data", "evidence": []}
    return {
        "status": "available",
        "low_kes": min(prices),
        "median_kes": int(statistics.median(prices)),
        "high_kes": max(prices),
        "evidence": evidence,
        "advisory_only": True,
    }
