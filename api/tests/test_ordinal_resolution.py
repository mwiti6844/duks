from __future__ import annotations

from . import sse_helper as sse


def test_compare_first_two_resolves_from_display_state(client, auth):
    sid = "sess-ordinal"
    # First search populates displayed_used_car_ids in session state.
    search = sse.chat(client, auth, "Find me a Subaru Forester under 2.5M", sid)
    shown = sse.components(search)[0]["props"]["cars"]
    assert len(shown) >= 2

    # "compare the first two" must resolve deterministically — no LLM ordinal parsing.
    compare = sse.chat(client, auth, "Compare the first two", sid)
    table = next(c for c in sse.components(compare) if c["type"] == "comparison_table")
    compared_ids = [c["id"] for c in table["props"]["cars"]]
    assert compared_ids == [shown[0]["id"], shown[1]["id"]]


def test_compare_without_results_declines(client, auth):
    events = sse.chat(client, auth, "Compare the first two", "sess-empty-compare")
    assert not sse.components(events)  # nothing to compare
    assert "search" in sse.text(events).lower()


def test_named_and_numeric_comparison_references_follow_conversation(client, auth):
    sid = "sess-contextual-compare"
    search = sse.chat(client, auth, "What options do I have below 1.5M?", sid)
    shown = next(
        component for component in sse.components(search)
        if component["type"] == "car_card_list"
    )["props"]["cars"]

    nissan_ad = next(
        car for car in shown
        if car["year"] == 2007 and car["make"] == "Nissan" and car["model"] == "AD"
    )
    demio = next(
        car for car in shown
        if car["year"] == 2016 and car["make"] == "Mazda" and car["model"] == "Demio"
    )
    note_2018 = next(
        car for car in shown
        if car["year"] == 2018 and car["make"] == "Nissan" and car["model"] == "Note"
    )

    sse.chat(client, auth, "Tell me more about the 2007 Nissan AD", sid)
    compare_demio = sse.chat(
        client, auth, "How does this compare to the 2016 Mazda Demio?", sid
    )
    table = next(
        component for component in sse.components(compare_demio)
        if component["type"] == "comparison_table"
    )
    assert [car["id"] for car in table["props"]["cars"]] == [
        nissan_ad["id"], demio["id"]
    ]

    compare_second = sse.chat(
        client,
        auth,
        "What of the 2018 Nissan Note, how does it compare against the 2?",
        sid,
    )
    table = next(
        component for component in sse.components(compare_second)
        if component["type"] == "comparison_table"
    )
    assert [car["id"] for car in table["props"]["cars"]] == [
        note_2018["id"], shown[1]["id"]
    ]


def test_comparison_followups_are_named_and_do_not_repeat_current_pair(client, auth):
    sid = "sess-smart-compare-followups"
    search = sse.chat(client, auth, "What options do I have below 1.5M?", sid)
    shown = next(
        component for component in sse.components(search)
        if component["type"] == "car_card_list"
    )["props"]["cars"]
    compare = sse.chat(client, auth, "Compare the first two", sid)
    followups = next(
        component for component in sse.components(compare)
        if component["type"] == "follow_up_suggestions"
    )["props"]["suggestions"]
    comparison_actions = [
        item for item in followups if item["action"]["type"] == "compare_cars"
    ]
    assert comparison_actions
    assert all("Compare with the " in item["label"] for item in comparison_actions)
    current_pair = {shown[0]["id"], shown[1]["id"]}
    assert all(
        set(item["action"]["entity_ids"]) != current_pair
        for item in comparison_actions
    )


def test_compare_cheapest_and_most_expensive_resolves_visible_extremes(client, auth):
    sid = "sess-compare-extremes"
    search = sse.chat(client, auth, "Show cars below 2M", sid)
    shown = next(
        component for component in sse.components(search)
        if component["type"] == "car_card_list"
    )["props"]["cars"]
    events = sse.chat(client, auth, "Compare the cheapest and most expensive", sid)
    compared = next(
        component for component in sse.components(events)
        if component["type"] == "comparison_table"
    )["props"]["cars"]
    assert {car["id"] for car in compared} == {
        min(shown, key=lambda car: car["price_kes"])["id"],
        max(shown, key=lambda car: car["price_kes"])["id"],
    }
