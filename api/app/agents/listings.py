"""Listings Agent: multi-turn, LLM-assisted structured slot extraction.

Sticky routing keeps mid-draft turns here. The LLM extracts only values the user
actually supplied; deterministic validation controls what enters Redis/SQLite.
No vehicle attributes are fabricated or defaulted.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from collections.abc import Callable

from .. import listingsign
from ..db import repositories as repo
from ..listing_pricing import price_guidance
from ..listing_validation import blocking_issues, completion, validate_listing
from ..prompts import load_prompt
from .deps import Deps
from .events import ComponentReady, TextDelta, ToolCompleted, ToolStarted, Trace
from .state import GraphState

Emit = Callable[[object], None]

# Required slots, in the order we ask for them. These are all persisted listing
# attributes; image_url remains optional and uses a visual placeholder when absent.
_SLOTS = (
    "make", "model", "year", "mileage_km", "price_kes", "transmission",
    "fuel", "condition", "body_type", "location", "description",
)

_ASK = {
    "make": "What's the make of your car?",
    "model": "What model is it?",
    "year": "What year is it?",
    "mileage_km": "Roughly how many kilometres has it done?",
    "price_kes": "And what price would you like to list it at? (in KES)",
    "transmission": "Is it automatic or manual?",
    "fuel": "What fuel does it use?",
    "condition": "How would you describe its condition?",
    "body_type": "What body type is it (for example SUV, sedan, or hatchback)?",
    "location": "Where is the car located?",
    "description": (
        "Tell me a few honest details for the description—features, maintenance, "
        "condition notes, or anything a buyer should know."
    ),
}


def _next_missing(fields: dict) -> str | None:
    for slot in _SLOTS:
        if fields.get(slot) in (None, "", 0):
            return slot
    return None


def _validated_fields(raw: object) -> dict:
    """Allow-list and validate extracted values. Invalid/unknown values are ignored."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    current_year = datetime.now(timezone.utc).year
    for key in _SLOTS:
        value = raw.get(key)
        if value in (None, "", 0):
            continue
        if key in ("year", "mileage_km", "price_kes"):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if key == "year" and not 1900 <= number <= current_year + 1:
                continue
            if key != "year" and number <= 0:
                continue
            out[key] = number
        elif isinstance(value, str):
            cleaned = re.sub(r"\s+", " ", value).strip()
            if 1 <= len(cleaned) <= 80:
                out[key] = cleaned
    return out


def _extract_fields(message: str, current: str | None, fields: dict, deps: Deps) -> tuple[dict, str]:
    system, version = load_prompt("listings.v1")
    payload = json.dumps({
        "current_missing_field": current,
        "already_collected": fields,
        "latest_user_message": message,
    })
    result = deps.llm.complete_json(system=system, user=payload, max_tokens=400)
    return _validated_fields(result.get("fields")), version


def handle_sell(state: GraphState, deps: Deps, emit: Emit) -> None:
    sid = state["session_id"]
    owner_id = state["user_id"]
    cached = deps.sessions.get_listing_draft(sid)
    with deps.db_factory() as db:
        durable = (
            repo.get_listing_draft(db, cached["draft_id"], owner_id)
            if cached and cached.get("draft_id")
            else None
        )
        draft = repo.listing_draft_payload(db, durable) if durable else {
            "draft_id": listingsign.new_draft_id(),
            "fields": {},
            "status": "collecting",
            "revision": 1,
            "mode": "create",
            "target_listing_id": None,
            "images": [],
        }
    fields = dict(draft.get("fields", {}))

    current = _next_missing(fields)
    emit(ToolStarted(name="extract_listing_fields", params={"asking": current}))
    t0 = time.time()
    try:
        parsed, prompt_version = _extract_fields(state["message"], current, fields, deps)
    except Exception:
        parsed, prompt_version = {}, "listings.v1"
    changes = {k: v for k, v in parsed.items() if v not in (None, "", 0)}
    changed = any(fields.get(key) != value for key, value in changes.items())
    fields.update(changes)
    emit(ToolCompleted(name="extract_listing_fields", ms=int((time.time() - t0) * 1000),
                       detail={"filled": [s for s in _SLOTS if fields.get(s)]}))
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": prompt_version}))

    missing = _next_missing(fields)
    if missing:
        progress, missing_fields = completion(fields)
        issues = validate_listing(fields, image_count=len(draft.get("images", [])))
        with deps.db_factory() as db:
            row = repo.save_listing_draft(
                db,
                draft_id=draft["draft_id"],
                owner_id=owner_id,
                fields=fields,
                status="collecting",
                validation=issues,
                guidance={},
                mode=draft.get("mode", "create"),
                target_listing_id=draft.get("target_listing_id"),
                increment_revision=changed and bool(durable),
            )
            draft = repo.listing_draft_payload(db, row)
        deps.sessions.save_listing_draft(sid, draft)
        ack = "Got it. " if parsed else ""
        emit(ComponentReady(type="listing_progress", props={
            "draft_id": draft["draft_id"],
            "percent": progress,
            "missing_fields": missing_fields,
            "status": "collecting",
        }))
        emit(TextDelta(text=f"{ack}{_ASK[missing]}"))
        return

    # All user-supplied slots collected → validate, price, persist, sign and review.
    full = {
        "make": fields["make"],
        "model": fields["model"],
        "year": int(fields["year"]),
        "price_kes": int(fields["price_kes"]),
        "mileage_km": int(fields["mileage_km"]),
        "transmission": fields["transmission"],
        "fuel": fields["fuel"],
        "condition": fields["condition"],
        "body_type": fields["body_type"],
        "location": fields["location"],
        "description": fields["description"],
        "image_url": "",
    }
    with deps.db_factory() as db:
        guidance = price_guidance(db, full)
        issues = validate_listing(full, image_count=len(draft.get("images", [])))
        status = "ready_to_publish" if not blocking_issues(issues) else "needs_review"
        row = repo.save_listing_draft(
            db,
            draft_id=draft["draft_id"],
            owner_id=owner_id,
            fields=full,
            status=status,
            validation=issues,
            guidance=guidance,
            mode=draft.get("mode", "create"),
            target_listing_id=draft.get("target_listing_id"),
            increment_revision=changed and bool(durable),
        )
        draft = repo.listing_draft_payload(db, row)
    image_ids = [image["id"] for image in draft.get("images", [])]
    signed = listingsign.make_signed_draft(
        deps.settings.bid_signing_secret,
        listingsign.create_draft(
            owner_id=owner_id,
            fields=full,
            draft_id=draft["draft_id"],
            revision=draft["revision"],
            mode=draft["mode"],
            target_listing_id=draft.get("target_listing_id"),
            image_ids=image_ids,
        ),
    )
    draft.update({"fields": full, "signed": signed})
    deps.sessions.save_listing_draft(sid, draft)
    emit(Trace(kind="routing", label="listing_ready", detail={"draft_id": draft["draft_id"]}))

    emit(ComponentReady(type="listing_summary", props={
        "draft_id": draft["draft_id"],
        **full,
        "signed_draft": signed,
        "revision": draft["revision"],
        "status": draft["status"],
        "progress": 100,
        "validation": draft["validation"],
        "guidance": draft["guidance"],
        "images": draft["images"],
        "mode": draft["mode"],
    }))
    emit(TextDelta(text=(
        f"Here's your {full['year']} {full['make']} {full['model']} listing at "
        f"KES {full['price_kes']:,}. Review it and tap Confirm to publish, or Cancel to discard."
    )))
