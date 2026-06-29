from __future__ import annotations

from . import sse_helper as sse


def test_bid_streams_confirm_modal_without_persisting(client, auth):
    sid = "sess-bid"
    sse.chat(client, auth, "Show me auctions", sid)
    events = sse.chat(client, auth, "Bid 1.8M on the Subaru Forester", sid)
    modal = next(c for c in sse.components(events) if c["type"] == "bid_confirm_modal")
    assert modal["props"]["amount_kes"] == 1_800_000
    assert "signed_proposal" in modal["props"]

    # No bid persisted yet.
    bids = client.get("/api/bids", headers=auth).json()
    assert all(b["amount_kes"] != 1_800_000 for b in bids)


def test_bid_below_minimum_rejected(client, auth):
    sid = "sess-bid-low"
    sse.chat(client, auth, "Show me auctions", sid)
    events = sse.chat(client, auth, "Bid 100000 on the Subaru Forester", sid)
    assert not any(c["type"] == "bid_confirm_modal" for c in sse.components(events))
    assert "at least" in sse.text(events).lower()


def test_confirm_persists_then_idempotent(client, auth):
    sid = "sess-bid-confirm"
    sse.chat(client, auth, "Show me auctions", sid)
    events = sse.chat(client, auth, "Bid 1.85M on the Subaru Forester", sid)
    modal = next(c for c in sse.components(events) if c["type"] == "bid_confirm_modal")
    signed = modal["props"]["signed_proposal"]

    r1 = client.post("/api/bids/confirm", headers=auth,
                     json={"signed_proposal": signed, "session_id": sid})
    assert r1.status_code == 200
    assert r1.json()["created"] is True
    bid_id = r1.json()["bid"]["id"]

    # Idempotent retry of the SAME proposal returns the existing receipt, no new bid.
    r2 = client.post("/api/bids/confirm", headers=auth,
                     json={"signed_proposal": signed, "session_id": sid})
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["bid"]["id"] == bid_id


def test_confirm_requires_matching_pending_session(client, auth):
    sid = "sess-bid-owner"
    sse.chat(client, auth, "Show me auctions", sid)
    events = sse.chat(client, auth, "Bid 2.0M on the Subaru Forester", sid)
    modal = next(c for c in sse.components(events) if c["type"] == "bid_confirm_modal")

    response = client.post(
        "/api/bids/confirm",
        headers=auth,
        json={
            "signed_proposal": modal["props"]["signed_proposal"],
            "session_id": "sess-wrong-owner",
        },
    )
    assert response.status_code == 409
