"""Expiring, signed bid proposals for the human-in-the-loop bid gate.

A proposal is created during chat (Transaction tool), streamed to the client as a
bid_confirm_modal, and stored in Redis. Only POST /api/bids/confirm persists a bid,
and only after verifying the HMAC signature + expiry. A random proposal_id/nonce
plus a UNIQUE DB constraint give replay protection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

_PROPOSAL_TTL_SECONDS = 60 * 10  # 10 minutes


@dataclass(frozen=True)
class BidProposal:
    proposal_id: str
    user_id: str
    auction_id: str
    amount_kes: int
    expires_at: int  # unix seconds

    def to_payload(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "user_id": self.user_id,
            "auction_id": self.auction_id,
            "amount_kes": self.amount_kes,
            "expires_at": self.expires_at,
        }


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(secret: str, payload: dict) -> str:
    return hmac.new(secret.encode(), _canonical(payload), hashlib.sha256).hexdigest()


def create_proposal(
    *, user_id: str, auction_id: str, amount_kes: int
) -> BidProposal:
    return BidProposal(
        proposal_id=f"prop_{uuid.uuid4().hex}",
        user_id=user_id,
        auction_id=auction_id,
        amount_kes=amount_kes,
        expires_at=int(time.time()) + _PROPOSAL_TTL_SECONDS,
    )


def make_signed_proposal(secret: str, proposal: BidProposal) -> dict:
    payload = proposal.to_payload()
    return {**payload, "signature": sign(secret, payload)}


class ProposalError(Exception):
    pass


def verify_signed_proposal(secret: str, signed: dict) -> BidProposal:
    """Verify signature + expiry. Raises ProposalError on any mismatch."""
    signature = signed.get("signature")
    if not signature:
        raise ProposalError("Missing signature")
    payload = {k: signed[k] for k in ("proposal_id", "user_id", "auction_id", "amount_kes", "expires_at") if k in signed}
    if len(payload) != 5:
        raise ProposalError("Malformed proposal")
    expected = sign(secret, payload)
    if not hmac.compare_digest(expected, signature):
        raise ProposalError("Bad signature")
    if int(payload["expires_at"]) < int(time.time()):
        raise ProposalError("Proposal expired")
    return BidProposal(
        proposal_id=payload["proposal_id"],
        user_id=payload["user_id"],
        auction_id=payload["auction_id"],
        amount_kes=int(payload["amount_kes"]),
        expires_at=int(payload["expires_at"]),
    )
