from __future__ import annotations

import time

from app import bidsign


def test_tampered_signature_rejected():
    secret = "s3cret"
    proposal = bidsign.create_proposal(user_id="usr_david", auction_id="auc_for_01", amount_kes=1_800_000)
    signed = bidsign.make_signed_proposal(secret, proposal)
    signed["amount_kes"] = 1  # tamper after signing
    try:
        bidsign.verify_signed_proposal(secret, signed)
        assert False, "expected ProposalError"
    except bidsign.ProposalError:
        pass


def test_expired_proposal_rejected():
    secret = "s3cret"
    proposal = bidsign.BidProposal(
        proposal_id="prop_x", user_id="u", auction_id="a", amount_kes=10,
        expires_at=int(time.time()) - 5,
    )
    signed = bidsign.make_signed_proposal(secret, proposal)
    try:
        bidsign.verify_signed_proposal(secret, signed)
        assert False, "expected ProposalError"
    except bidsign.ProposalError:
        pass


def test_wrong_secret_rejected():
    proposal = bidsign.create_proposal(user_id="u", auction_id="a", amount_kes=10)
    signed = bidsign.make_signed_proposal("secret-a", proposal)
    try:
        bidsign.verify_signed_proposal("secret-b", signed)
        assert False, "expected ProposalError"
    except bidsign.ProposalError:
        pass


def test_confirm_rejects_tampered_proposal_via_api(client, auth):
    from . import sse_helper as sse

    sid = "sess-replay"
    sse.chat(client, auth, "Show me auctions", sid)
    events = sse.chat(client, auth, "Bid 1.9M on the Subaru Forester", sid)
    modal = next(c for c in sse.components(events) if c["type"] == "bid_confirm_modal")
    signed = dict(modal["props"]["signed_proposal"])
    signed["amount_kes"] = 999_999_999  # tamper

    resp = client.post("/api/bids/confirm", headers=auth,
                       json={"signed_proposal": signed, "session_id": sid})
    assert resp.status_code == 400
