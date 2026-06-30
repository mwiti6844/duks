from __future__ import annotations

from . import sse_helper as sse


def _ready(client, auth, sid: str) -> dict:
    turns = (
        "Sell my 2016 Toyota Fielder",
        "120,000 km",
        "1.4M",
        "Automatic",
        "Petrol",
        "Good",
        "Station Wagon",
        "Kiambu",
        "Well maintained family car with a clean interior.",
    )
    events = []
    for turn in turns:
        events = sse.chat(client, auth, turn, sid)
    return next(
        item["props"] for item in sse.components(events)
        if item["type"] == "listing_summary"
    )


def test_draft_autosaves_and_resumes_across_browser_sessions(client, auth):
    props = _ready(client, auth, "sess-durable-one")
    restored = client.get(
        "/api/session/bootstrap",
        headers=auth,
        params={"session_id": "sess-durable-two"},
    ).json()["listing_draft"]
    assert restored["draft_id"] == props["draft_id"]
    assert restored["status"] == "ready_to_publish"
    assert restored["fields"]["description"]
    assert restored["signed"]["revision"] == restored["revision"]


def test_edit_invalidates_old_signed_preview(client, auth):
    sid = "sess-stale-listing-preview"
    props = _ready(client, auth, sid)
    old_signed = props["signed_draft"]
    changed = client.patch(
        f"/api/listing-drafts/{props['draft_id']}",
        headers=auth,
        json={"fields": {"price_kes": 1_500_000}},
    )
    assert changed.status_code == 200
    assert changed.json()["revision"] > props["revision"]
    stale = client.post(
        "/api/listings/confirm",
        headers=auth,
        json={"signed_draft": old_signed, "session_id": sid},
    )
    assert stale.status_code == 409


def test_guidance_is_advisory_and_uses_sale_evidence(client, auth):
    props = _ready(client, auth, "sess-guidance")
    guidance = props["guidance"]
    assert guidance["status"] == "available"
    assert guidance["advisory_only"] is True
    assert guidance["evidence"]


def test_published_listing_edit_requires_new_confirm(client, auth):
    sid = "sess-published-edit"
    props = _ready(client, auth, sid)
    created = client.post(
        "/api/listings/confirm",
        headers=auth,
        json={"signed_draft": props["signed_draft"], "session_id": sid},
    ).json()["listing"]

    draft = client.post(f"/api/listings/{created['id']}/edit", headers=auth).json()
    client.patch(
        f"/api/listing-drafts/{draft['draft_id']}",
        headers=auth,
        json={"fields": {"price_kes": 1_550_000}},
    )
    review = client.post(
        f"/api/listing-drafts/{draft['draft_id']}/review", headers=auth
    )
    assert review.status_code == 200, review.text
    confirmed = client.post(
        "/api/listings/confirm",
        headers=auth,
        json={
            "signed_draft": review.json()["signed_draft"],
            "session_id": "sess-edit-confirm",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["listing"]["id"] == created["id"]
    assert confirmed.json()["listing"]["price_kes"] == 1_550_000


def test_cloudinary_is_optional_and_registration_is_validated(client, auth):
    assert client.get("/api/media/cloudinary/signature", headers=auth).status_code == 503
    props = _ready(client, auth, "sess-photo-validation")
    invalid = client.post(
        f"/api/listing-drafts/{props['draft_id']}/images",
        headers=auth,
        json={
            "public_id": "carduka/usr_david/photo",
            "secure_url": "https://example.com/not-cloudinary.jpg",
            "width": 100,
            "height": 100,
            "format": "jpg",
            "bytes": 1000,
        },
    )
    assert invalid.status_code == 400
