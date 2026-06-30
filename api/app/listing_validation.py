"""Deterministic listing validation. LLM output never decides publish readiness."""
from __future__ import annotations

from datetime import datetime, timezone

REQUIRED_FIELDS = (
    "make", "model", "year", "mileage_km", "price_kes", "transmission",
    "fuel", "condition", "body_type", "location", "description",
)


def validate_listing(fields: dict, *, image_count: int = 0) -> list[dict]:
    issues: list[dict] = []
    for field in REQUIRED_FIELDS:
        if fields.get(field) in (None, "", 0):
            issues.append({
                "field": field, "level": "error",
                "message": f"{field.replace('_', ' ').title()} is required.",
            })
    year = fields.get("year")
    if year is not None and not 1900 <= int(year) <= datetime.now(timezone.utc).year + 1:
        issues.append({"field": "year", "level": "error", "message": "Enter a valid year."})
    mileage = fields.get("mileage_km")
    if mileage is not None and int(mileage) < 0:
        issues.append({"field": "mileage_km", "level": "error",
                       "message": "Mileage cannot be negative."})
    if mileage is not None and int(mileage) > 1_000_000:
        issues.append({"field": "mileage_km", "level": "warning",
                       "message": "This mileage is unusually high; please confirm it."})
    price = fields.get("price_kes")
    if price is not None and int(price) <= 0:
        issues.append({"field": "price_kes", "level": "error",
                       "message": "Asking price must be greater than zero."})
    if not image_count:
        issues.append({"field": "photos", "level": "warning",
                       "message": "No photos added. The listing will use a placeholder."})
    return issues


def blocking_issues(issues: list[dict]) -> list[dict]:
    return [issue for issue in issues if issue.get("level") == "error"]


def completion(fields: dict) -> tuple[int, list[str]]:
    missing = [field for field in REQUIRED_FIELDS if fields.get(field) in (None, "", 0)]
    complete = len(REQUIRED_FIELDS) - len(missing)
    return round(complete / len(REQUIRED_FIELDS) * 100), missing
