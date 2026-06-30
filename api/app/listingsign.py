"""Expiring, signed listing drafts for the seller confirm gate.

Mirrors app/bidsign.py. A draft is built when the slot-filling conversation is
complete, streamed to the client as a listing_summary, and stored user-scoped in
Redis. Only POST /api/listings/confirm persists a listing, after verifying the HMAC
signature + expiry + ownership. A random draft_id + a UNIQUE DB constraint
(`source_draft_id`) make confirmation idempotent and replay-safe.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

_DRAFT_TTL_SECONDS = 60 * 30  # 30 minutes — a sell conversation may take longer than a bid

# Fields the listing carries (kept in a stable order for signing/equality checks).
LISTING_FIELDS = ("make", "model", "year", "price_kes", "mileage_km",
                  "transmission", "fuel", "condition", "body_type", "location",
                  "description", "image_url")


@dataclass(frozen=True)
class ListingDraft:
    draft_id: str
    owner_id: str
    fields: dict
    expires_at: int
    revision: int = 1
    mode: str = "create"
    target_listing_id: str | None = None
    image_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict:
        return {
            "draft_id": self.draft_id,
            "owner_id": self.owner_id,
            "fields": self.fields,
            "expires_at": self.expires_at,
            "revision": self.revision,
            "mode": self.mode,
            "target_listing_id": self.target_listing_id,
            "image_ids": list(self.image_ids),
        }


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(secret: str, payload: dict) -> str:
    return hmac.new(secret.encode(), _canonical(payload), hashlib.sha256).hexdigest()


def new_draft_id() -> str:
    return f"draft_{uuid.uuid4().hex}"


def create_draft(
    *, owner_id: str, fields: dict, draft_id: str | None = None, revision: int = 1,
    mode: str = "create", target_listing_id: str | None = None,
    image_ids: list[str] | None = None,
) -> ListingDraft:
    return ListingDraft(
        draft_id=draft_id or new_draft_id(),
        owner_id=owner_id,
        fields={k: fields.get(k) for k in LISTING_FIELDS},
        expires_at=int(time.time()) + _DRAFT_TTL_SECONDS,
        revision=revision,
        mode=mode,
        target_listing_id=target_listing_id,
        image_ids=tuple(image_ids or []),
    )


def make_signed_draft(secret: str, draft: ListingDraft) -> dict:
    payload = draft.to_payload()
    return {**payload, "signature": sign(secret, payload)}


class DraftError(Exception):
    pass


def verify_signed_draft(secret: str, signed: dict) -> ListingDraft:
    """Verify signature + expiry. Raises DraftError on any mismatch."""
    signature = signed.get("signature")
    if not signature:
        raise DraftError("Missing signature")
    keys = (
        "draft_id", "owner_id", "fields", "expires_at", "revision", "mode",
        "target_listing_id", "image_ids",
    )
    payload = {k: signed[k] for k in keys if k in signed}
    if len(payload) != len(keys) or not isinstance(payload["fields"], dict):
        raise DraftError("Malformed draft")
    expected = sign(secret, payload)
    if not hmac.compare_digest(expected, signature):
        raise DraftError("Bad signature")
    if int(payload["expires_at"]) < int(time.time()):
        raise DraftError("Draft expired")
    return ListingDraft(
        draft_id=payload["draft_id"],
        owner_id=payload["owner_id"],
        fields=payload["fields"],
        expires_at=int(payload["expires_at"]),
        revision=int(payload["revision"]),
        mode=str(payload["mode"]),
        target_listing_id=payload["target_listing_id"],
        image_ids=tuple(payload["image_ids"]),
    )
