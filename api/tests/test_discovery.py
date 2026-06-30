from __future__ import annotations

from . import sse_helper as sse


def test_search_returns_car_cards(client, auth):
    events = sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", "sess-search")
    comps = sse.components(events)
    assert any(c["type"] == "car_card_list" for c in comps)
    car_list = next(c for c in comps if c["type"] == "car_card_list")
    cars = car_list["props"]["cars"]
    assert cars and all(c["price_kes"] <= 2_500_000 for c in cars)
    assert all(c["make"] == "Subaru" for c in cars)


def test_broad_buy_request_starts_conversational_intake_without_catalogue_dump(
    client, auth
):
    events = sse.chat(client, auth, "I'd like to buy a car", "sess-natural-buy")
    comps = sse.components(events)
    tools = [data for event, data in events if event == "tool"]

    assert any(event == "token" for event, _ in events)
    assert not any(c["type"] == "car_card_list" for c in comps)
    assert not any(t["name"] == "search_cars" for t in tools)


def test_buy_intake_collects_preferences_then_searches(client, auth):
    sid = "sess-buy-intake"
    first = sse.chat(client, auth, "I want to buy a car", sid)
    assert any(event == "token" for event, _ in first)

    second = sse.chat(client, auth, "Mostly family trips and the school run", sid)
    assert any(event == "token" for event, _ in second)
    assert not any(c["type"] == "car_card_list" for c in sse.components(second))

    third = sse.chat(client, auth, "My budget is KES 2.5M", sid)
    car_list = next(
        c for c in sse.components(third) if c["type"] == "car_card_list"
    )
    assert car_list["props"]["cars"]
    assert len(car_list["props"]["cars"]) <= 8
    assert all(c["price_kes"] <= 2_500_000 for c in car_list["props"]["cars"])
    assert all(
        c["body_type"] in {"SUV", "Station Wagon"}
        for c in car_list["props"]["cars"]
    )


def test_natural_language_range_and_mileage_constraints_reach_database(client, auth):
    events = sse.chat(
        client,
        auth,
        "I'd like a low mileage car, under 150000 km and between 800k and 2m",
        "sess-rich-search",
    )
    car_list = next(
        c for c in sse.components(events) if c["type"] == "car_card_list"
    )
    cars = car_list["props"]["cars"]

    assert cars
    assert all(800_000 <= car["price_kes"] <= 2_000_000 for car in cars)
    assert all(car["mileage_km"] <= 150_000 for car in cars)
    assert [car["mileage_km"] for car in cars] == sorted(
        car["mileage_km"] for car in cars
    )

    started = next(
        data for event, data in events
        if event == "tool" and data["name"] == "search_cars"
        and data["status"] == "started"
    )
    assert started["params"]["min_price_kes"] == 800_000
    assert started["params"]["max_price_kes"] == 2_000_000
    assert started["params"]["max_mileage_km"] == 150_000
    assert started["params"]["sort_by"] == "mileage_asc"


def test_followup_refines_previous_search_and_can_remove_constraint(client, auth):
    sid = "sess-search-refine"
    first = sse.chat(
        client,
        auth,
        "Find cars between 800k and 2m under 150000 km",
        sid,
    )
    assert any(c["type"] == "car_card_list" for c in sse.components(first))

    refined = sse.chat(client, auth, "Make them automatic and in Nairobi", sid)
    cars = next(
        c for c in sse.components(refined) if c["type"] == "car_card_list"
    )["props"]["cars"]
    assert cars
    assert all(800_000 <= car["price_kes"] <= 2_000_000 for car in cars)
    assert all(car["mileage_km"] <= 150_000 for car in cars)
    assert all(car["transmission"] == "Automatic" for car in cars)
    assert all("Nairobi" in car["location"] for car in cars)

    widened = sse.chat(client, auth, "Ignore the mileage limit", sid)
    started = next(
        data for event, data in widened
        if event == "tool" and data["name"] == "search_cars"
        and data["status"] == "started"
    )
    assert "max_mileage_km" not in started["params"]


def test_followup_loads_exact_displayed_car_from_db(client, auth):
    sid = "sess-car-details"
    sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    events = sse.chat(client, auth, "Tell me more about the 2015 Subaru Forester", sid)

    cards = [c for c in sse.components(events) if c["type"] == "car_card"]
    assert len(cards) == 1
    assert cards[0]["props"]["year"] == 2015
    assert cards[0]["props"]["make"] == "Subaru"
    assert cards[0]["props"]["model"] == "Forester"
    tools = [data for event, data in events if event == "tool"]
    assert any(t["name"] == "get_displayed_car" and t["status"] == "completed"
               and t["detail"]["car_id"] for t in tools)


def test_followup_can_resolve_unique_year_reference(client, auth):
    sid = "sess-car-year-reference"
    sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    events = sse.chat(client, auth, "What about the 2017 one?", sid)
    card = next(c for c in sse.components(events) if c["type"] == "car_card")
    assert card["props"]["year"] == 2017


def test_pronoun_resolves_focused_database_row(client, auth):
    sid = "sess-focused-pronoun"
    search = sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    first = next(c for c in sse.components(search) if c["type"] == "car_card_list")
    focused = first["props"]["cars"][0]

    events = sse.chat(client, auth, "Tell me more about it", sid)
    card = next(c for c in sse.components(events) if c["type"] == "car_card")
    assert card["props"]["id"] == focused["id"]


def test_detail_reference_resolves_displayed_ordinal(client, auth):
    sid = "sess-detail-ordinal"
    search = sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    cars = next(c for c in sse.components(search) if c["type"] == "car_card_list")
    events = sse.chat(client, auth, "Tell me more about the second one", sid)
    card = next(c for c in sse.components(events) if c["type"] == "car_card")
    assert card["props"]["id"] == cars["props"]["cars"][1]["id"]


def test_auctions_returns_countdown(client, auth):
    events = sse.chat(client, auth, "Show me auctions", "sess-auc")
    comps = sse.components(events)
    assert any(c["type"] == "auction_countdown" for c in comps)
    auctions = next(c for c in comps if c["type"] == "auction_countdown")["props"]["auctions"]
    assert auctions
    assert all("ends_at" in a and "min_next_bid_kes" in a for a in auctions)


def test_done_event_present(client, auth):
    events = sse.chat(client, auth, "Find a Toyota Fielder", "sess-done")
    assert events[-1][0] == "done"
