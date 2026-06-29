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
from ..prompts import load_prompt
from .deps import Deps
from .events import ComponentReady, TextDelta, ToolCompleted, ToolStarted, Trace
from .state import GraphState

Emit = Callable[[object], None]

# Required slots, in the order we ask for them. These are all persisted listing
# attributes; image_url remains optional and uses a visual placeholder when absent.
_SLOTS = (
    "make", "model", "year", "mileage_km", "price_kes", "transmission",
    "fuel", "condition", "body_type", "location",
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
    draft = deps.sessions.get_listing_draft(sid) or {
        "draft_id": listingsign.new_draft_id(),
        "fields": {},
        "status": "collecting",
    }
    fields = dict(draft.get("fields", {}))

    current = _next_missing(fields)
    emit(ToolStarted(name="extract_listing_fields", params={"asking": current}))
    t0 = time.time()
    try:
        parsed, prompt_version = _extract_fields(state["message"], current, fields, deps)
    except Exception:
        parsed, prompt_version = {}, "listings.v1"
    fields.update({k: v for k, v in parsed.items() if v not in (None, "", 0)})
    emit(ToolCompleted(name="extract_listing_fields", ms=int((time.time() - t0) * 1000),
                       detail={"filled": [s for s in _SLOTS if fields.get(s)]}))
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": prompt_version}))

    missing = _next_missing(fields)
    if missing:
        draft["fields"] = fields
        draft["status"] = "collecting"
        deps.sessions.save_listing_draft(sid, draft)
        ack = "Got it. " if parsed else ""
        emit(TextDelta(text=f"{ack}{_ASK[missing]}"))
        return

    # All user-supplied slots collected → sign and present the summary.
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
        "image_url": "",
    }
    signed = listingsign.make_signed_draft(
        deps.settings.bid_signing_secret,
        listingsign.create_draft(owner_id=owner_id, fields=full, draft_id=draft["draft_id"]),
    )
    draft.update({"fields": full, "status": "ready", "signed": signed})
    deps.sessions.save_listing_draft(sid, draft)
    emit(Trace(kind="routing", label="listing_ready", detail={"draft_id": draft["draft_id"]}))

    emit(ComponentReady(type="listing_summary", props={
        "draft_id": draft["draft_id"],
        **full,
        "signed_draft": signed,
    }))
    emit(TextDelta(text=(
        f"Here's your {full['year']} {full['make']} {full['model']} listing at "
        f"KES {full['price_kes']:,}. Review it and tap Confirm to publish, or Cancel to discard."
    )))
