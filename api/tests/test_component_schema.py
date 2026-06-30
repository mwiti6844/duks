from __future__ import annotations

from app.agents.events import ComponentReady, TextDelta
from app.agents.result import ComponentType, validate_component
from app.streaming.sse_adapter import events_to_sse


def test_validate_known_component():
    comp = validate_component(ComponentType.CAR_CARD, {
        "id": "x",
        "make": "Toyota",
        "model": "Fielder",
        "year": 2018,
        "price_kes": 1_700_000,
        "mileage_km": 80_000,
        "transmission": "Automatic",
        "fuel": "Petrol",
        "location": "Nairobi",
        "condition": "Excellent",
        "body_type": "Wagon",
        "image_url": "https://example.test/car.jpg",
    })
    assert comp is not None
    assert comp.type == ComponentType.CAR_CARD


def test_unknown_component_type_emits_error_frame():
    frames = list(events_to_sse([ComponentReady(type="totally_made_up", props={})]))
    joined = "".join(frames)
    assert "event: error" in joined
    assert "Unknown component type" in joined


def test_text_delta_serializes_to_token_frame():
    frames = list(events_to_sse([TextDelta(text="hello")]))
    joined = "".join(frames)
    assert "event: token" in joined
    assert "hello" in joined
    assert joined.strip().endswith('data: {}')  # done frame last


def test_valid_component_passes_through():
    frames = list(events_to_sse([
        ComponentReady(type="knowledge_answer", props={
            "answer": "Auctions are timed.",
            "citations": [{"source_id": "kb_1", "title": "Auctions", "score": 0.9}],
        })
    ]))
    joined = "".join(frames)
    assert "event: component" in joined
    assert "knowledge_answer" in joined


def test_invalid_known_component_props_are_dropped():
    frames = list(events_to_sse([ComponentReady(type="car_card", props={"id": "incomplete"})]))
    joined = "".join(frames)
    assert "event: component" not in joined
    assert "Invalid props" in joined


def _listing_props(**over):
    base = {
        "draft_id": "draft_x", "make": "Toyota", "model": "Fielder", "year": 2016,
        "price_kes": 1_400_000, "mileage_km": 120_000, "transmission": "Automatic",
        "fuel": "Petrol", "condition": "Good", "body_type": "Station Wagon",
        "location": "Kiambu", "image_url": "", "description": "Well maintained.",
        "signed_draft": {
            "draft_id": "draft_x", "owner_id": "usr_sarah", "fields": {},
            "expires_at": 9999999999, "revision": 1, "mode": "create",
            "target_listing_id": None, "image_ids": [], "signature": "abc",
        },
        "revision": 1, "status": "ready_to_publish", "progress": 100,
        "validation": [], "guidance": {}, "images": [], "mode": "create",
    }
    base.update(over)
    return base


def test_listing_summary_valid():
    comp = validate_component(ComponentType.LISTING_SUMMARY, _listing_props())
    assert comp is not None
    assert comp.type == ComponentType.LISTING_SUMMARY


def test_listing_summary_invalid_dropped():
    assert validate_component(ComponentType.LISTING_SUMMARY, {"make": "Toyota"}) is None
    assert validate_component(ComponentType.LISTING_SUMMARY, _listing_props(price_kes=0)) is None


def test_follow_up_suggestions_schema_is_strict():
    valid = {
        "suggestions": [{
            "id": "finance-car",
            "label": "Calculate financing",
            "action": {"type": "calculate_financing", "entity_id": "car_1"},
        }]
    }
    assert validate_component(ComponentType.FOLLOW_UP_SUGGESTIONS, valid) is not None
    invalid = {
        "suggestions": [{
            "id": "unsafe",
            "label": "Do something",
            "action": {"type": "delete_car", "entity_id": "car_1"},
        }]
    }
    assert validate_component(ComponentType.FOLLOW_UP_SUGGESTIONS, invalid) is None
