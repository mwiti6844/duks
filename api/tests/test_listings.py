from __future__ import annotations

from app import listingsign

from . import sse_helper as sse


def _sell_to_ready(client, auth, sid: str) -> dict:
    """Drive a full multi-turn sell flow and return the listing_summary props."""
    sse.chat(client, auth, "I want to sell my car", sid)
    sse.chat(client, auth, "Toyota Fielder", sid)
    sse.chat(client, auth, "2016", sid)
    sse.chat(client, auth, "120,000 km", sid)
    sse.chat(client, auth, "1.4M", sid)
    sse.chat(client, auth, "Automatic", sid)
    sse.chat(client, auth, "Petrol", sid)
    sse.chat(client, auth, "Good", sid)
    sse.chat(client, auth, "Station Wagon", sid)
    sse.chat(client, auth, "Kiambu", sid)
    events = sse.chat(
        client, auth,
        "Well maintained family car with regular servicing and a clean interior.",
        sid,
    )
    summary = next(c for c in sse.components(events) if c["type"] == "listing_summary")
    return summary["props"]


def test_multi_slot_first_turn_fills_make_model_year(client, auth):
    sid = "sess-multislot"
    events = sse.chat(client, auth, "Sell my 2016 Toyota Fielder", sid)
    # make+model+year captured in one turn → it should now ask for mileage, not year/make.
    assert "kilomet" in sse.text(events).lower()
    assert any(c["type"] == "listing_progress" for c in sse.components(events))
    assert not any(c["type"] == "listing_summary" for c in sse.components(events))


def test_full_flow_streams_listing_summary(client, auth):
    props = _sell_to_ready(client, auth, "sess-sell-full")
    assert props["make"] == "Toyota"
    assert props["model"] == "Fielder"
    assert props["year"] == 2016
    assert props["price_kes"] == 1_400_000
    assert props["mileage_km"] == 120_000
    assert props["body_type"] == "Station Wagon"  # inferred
    assert "signed_draft" in props


def test_confirm_then_idempotent(client, auth):
    sid = "sess-sell-confirm"
    props = _sell_to_ready(client, auth, sid)
    signed = props["signed_draft"]

    r1 = client.post("/api/listings/confirm", headers=auth,
                     json={"signed_draft": signed, "session_id": sid})
    assert r1.status_code == 200, r1.text
    assert r1.json()["created"] is True
    listing_id = r1.json()["listing"]["id"]
    assert r1.json()["listing"]["owner_id"]  # owned by the authenticated user

    # Second confirm of the same draft (Redis draft now cleared) returns the same row.
    r2 = client.post("/api/listings/confirm", headers=auth,
                     json={"signed_proposal": signed, "session_id": sid,
                           "signed_draft": signed})
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["listing"]["id"] == listing_id


def test_both_users_can_sell(client):
    """Every authenticated user can create a listing."""
    for username in ("david", "sarah"):
        tok = client.post("/api/auth/login",
                          json={"username": username, "password": "demo1234"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        props = _sell_to_ready(client, h, f"sess-persona-{username}")
        r = client.post("/api/listings/confirm", headers=h,
                        json={"signed_draft": props["signed_draft"],
                              "session_id": f"sess-persona-{username}"})
        assert r.status_code == 200 and r.json()["created"] is True


def test_cross_user_draft_isolation(client, auth):
    """A draft signed for one user cannot be confirmed by another."""
    props = _sell_to_ready(client, auth, "sess-iso")
    other = client.post("/api/auth/login",
                        json={"username": "sarah", "password": "demo1234"}).json()["token"]
    resp = client.post("/api/listings/confirm",
                       headers={"Authorization": f"Bearer {other}"},
                       json={"signed_draft": props["signed_draft"], "session_id": "sess-iso"})
    assert resp.status_code == 403


def test_tampered_draft_rejected(client, auth):
    sid = "sess-tamper"
    props = _sell_to_ready(client, auth, sid)
    signed = dict(props["signed_draft"])
    signed["fields"] = {**signed["fields"], "price_kes": 1}  # tamper after signing
    resp = client.post("/api/listings/confirm", headers=auth,
                       json={"signed_draft": signed, "session_id": sid})
    assert resp.status_code == 400


def test_confirm_without_matching_redis_draft_conflicts(client, auth):
    """A validly-signed draft with no prior row and no Redis state → 409."""
    sid = "sess-noredis"
    props = _sell_to_ready(client, auth, sid)
    # Cancel clears the Redis draft; the row was never created.
    client.post("/api/listings/cancel", headers=auth, json={"session_id": sid})
    resp = client.post("/api/listings/confirm", headers=auth,
                       json={"signed_draft": props["signed_draft"], "session_id": sid})
    assert resp.status_code == 409


def test_confirm_rejects_mismatch_in_defaulted_listing_fields(client, auth):
    """Every signed field, not only the conversational slots, must match Redis."""
    sid = "sess-field-mismatch"
    props = _sell_to_ready(client, auth, sid)
    signed = dict(props["signed_draft"])
    signed["fields"] = {**signed["fields"], "location": "Mombasa"}
    payload = {
        k: signed[k]
        for k in (
            "draft_id", "owner_id", "fields", "expires_at", "revision", "mode",
            "target_listing_id", "image_ids",
        )
    }
    signed["signature"] = listingsign.sign("test-bid-secret", payload)

    resp = client.post("/api/listings/confirm", headers=auth,
                       json={"signed_draft": signed, "session_id": sid})
    assert resp.status_code == 409


def test_sticky_routing_and_cancel(client, auth):
    sid = "sess-sticky"
    sse.chat(client, auth, "I want to sell my car", sid)
    # A mid-draft message that would otherwise route to search stays in the sell flow.
    events = sse.chat(client, auth, "Subaru Forester", sid)
    assert not any(c["type"] == "car_card_list" for c in sse.components(events))
    assert "year" in sse.text(events).lower()
    # Cancel exits the flow.
    cancelled = sse.chat(client, auth, "cancel", sid)
    assert not sse.components(cancelled)
    # After cancel, a search routes normally again.
    search = sse.chat(client, auth, "Find me a Toyota Harrier under 6M", sid)
    assert any(c["type"] == "car_card_list" for c in sse.components(search))


def test_listing_draft_can_pause_and_resume_without_being_deleted(client, auth):
    sid = "sess-pause-listing"
    sse.chat(client, auth, "I want to sell my car", sid)
    sse.chat(client, auth, "Audi", sid)

    paused = sse.chat(client, auth, "Pause this listing", sid)
    assert not any(c["type"] == "car_card_list" for c in sse.components(paused))

    search = sse.chat(client, auth, "Find me a Toyota Harrier under 6M", sid)
    assert any(c["type"] == "car_card_list" for c in sse.components(search))

    resumed = sse.chat(client, auth, "Resume listing", sid)
    assert "model" in sse.text(resumed).lower()
