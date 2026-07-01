from __future__ import annotations

from . import sse_helper as sse


def _search(client, auth, sid: str) -> list[dict]:
    # A make + price search returns enough real listings for cars[1]/cars[3] picks.
    events = sse.chat(client, auth, "Find me a Toyota under 6M", sid)
    return next(c for c in sse.components(events) if c["type"] == "car_card_list")[
        "props"
    ]["cars"]


def test_select_car_action_uses_validated_id_not_visible_label(client, auth):
    sid = "sess-action-select"
    cars = _search(client, auth, sid)
    selected = cars[1]
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Tell me about a completely different car",
            "session_id": sid,
            "action": {"type": "select_car", "entity_id": selected["id"]},
        },
    )
    assert response.status_code == 200
    events = []
    event_name = None
    import json
    for line in response.text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: ") and event_name:
            events.append((event_name, json.loads(line[6:])))
    card = next(data for event, data in events
                if event == "component" and data["type"] == "vehicle_detail")
    assert card["props"]["car"]["id"] == selected["id"]
    assert any(event == "trace" and data["label"] == "ui_action" for event, data in events)


def test_forged_undisplayed_car_action_is_rejected(client, auth):
    sid = "sess-action-forged"
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Open this car",
            "session_id": sid,
            "action": {"type": "select_car", "entity_id": "car_for_01"},
        },
    )
    assert response.status_code == 409
    bootstrap = client.get(
        "/api/session/bootstrap", headers=auth, params={"session_id": sid}
    ).json()
    assert bootstrap["turns"] == []


def test_compare_action_uses_explicit_visible_ids(client, auth):
    sid = "sess-action-compare"
    cars = _search(client, auth, sid)
    chosen = [cars[1]["id"], cars[3]["id"]]
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Compare these cars",
            "session_id": sid,
            "action": {"type": "compare_cars", "entity_ids": chosen},
        },
    )
    assert response.status_code == 200
    events = []
    event_name = None
    import json
    for line in response.text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: ") and event_name:
            events.append((event_name, json.loads(line[6:])))
    table = next(data for event, data in events
                 if event == "component" and data["type"] == "comparison_table")
    assert [car["id"] for car in table["props"]["cars"]] == chosen


def test_search_emits_executable_suggestions_and_turns_restore(client, auth):
    sid = "sess-action-restore"
    events = sse.chat(client, auth, "Find me a Toyota Harrier under 6M", sid)
    followups = next(
        component for component in sse.components(events)
        if component["type"] == "follow_up_suggestions"
    )
    assert followups["props"]["suggestions"]
    assert all("action" in item for item in followups["props"]["suggestions"])

    bootstrap = client.get(
        "/api/session/bootstrap", headers=auth, params={"session_id": sid}
    ).json()
    assistant = [turn for turn in bootstrap["turns"] if turn["role"] == "assistant"][-1]
    restored_types = [component["type"] for component in assistant["components"]]
    assert "car_card_list" in restored_types
    assert "follow_up_suggestions" in restored_types


def test_buy_journey_starts_intake_without_hidden_search(client, auth):
    sid = "sess-start-buy"
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Help me buy a car",
            "session_id": sid,
            "action": {"type": "start_journey", "journey": "buy_car"},
        },
    )
    assert response.status_code == 200
    assert "event: token" in response.text
    assert '"name": "search_cars"' not in response.text
    assert "Subaru Forester" not in response.text


def test_finance_journey_requires_real_principal_then_continues(client, auth):
    sid = "sess-start-finance"
    start = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Help me finance a car",
            "session_id": sid,
            "action": {"type": "start_journey", "journey": "finance_car"},
        },
    )
    assert start.status_code == 200
    assert "tell me its price" in start.text
    assert "financing_calculator" not in start.text
    assert "2000000" not in start.text

    followup = sse.chat(client, auth, "KES 2.5M", sid)
    calculator = next(
        component for component in sse.components(followup)
        if component["type"] == "financing_calculator"
    )
    assert calculator["props"]["price_kes"] == 2_500_000


def test_financing_understands_price_deposit_and_term_without_cross_talk(client, auth):
    sid = "sess-finance-natural"
    sse.chat(client, auth, "I want to finance a car", sid)
    followup = sse.chat(
        client,
        auth,
        "The car costs KES 2.5M and I can put down 30% over 36 months",
        sid,
    )
    calculator = next(
        component for component in sse.components(followup)
        if component["type"] == "financing_calculator"
    )
    assert calculator["props"]["price_kes"] == 2_500_000
    assert calculator["props"]["deposit_kes"] == 750_000
    assert calculator["props"]["deposit_pct"] == 30
    assert calculator["props"]["term_months"] == 36


def test_information_journey_routes_to_grounded_knowledge(client, auth):
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Tell me about vehicle insurance",
            "session_id": "sess-start-insurance",
            "action": {"type": "start_journey", "journey": "insurance"},
        },
    )
    assert response.status_code == 200
    assert "knowledge_answer" in response.text
    assert "kb_insurance" in response.text
