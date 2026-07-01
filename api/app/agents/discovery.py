"""Discovery Agent: search, compare, AI price verdict, browse auctions.

Worker functions emit transport-neutral AgentExecutionEvents via `emit`. Ordinal
references ("compare the first two") resolve from session display state, never the LLM.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

from ..db import repositories as repo
from ..prompts import load_prompt
from . import suggestions, tools
from .context import prompt_context
from .deps import Deps
from .events import ComponentReady, TextDelta, ToolCompleted, ToolStarted, Trace
from .state import GraphState

Emit = Callable[[object], None]

_SEARCH_FIELDS = {
    "make",
    "model",
    "max_price_kes",
    "min_price_kes",
    "max_mileage_km",
    "min_mileage_km",
    "min_year",
    "max_year",
    "body_types",
    "transmission",
    "fuel",
    "location",
    "use_case",
    "sort_by",
}


def _search_constraints(entities: dict) -> dict:
    """Keep only deterministic catalogue filters/intake context."""
    return {
        key: value
        for key, value in entities.items()
        if key in _SEARCH_FIELDS and value not in (None, "", [])
    }


def _starts_new_search(message: str) -> bool:
    text = message.lower()
    return any(phrase in text for phrase in (
        "new search",
        "start over",
        "start again",
        "clear filters",
        "show all",
        "browse all",
    ))


def _is_broad_buy_request(message: str, entities: dict) -> bool:
    """True when the user expressed buying intent but supplied no usable criteria."""
    if _search_constraints(entities):
        return False
    text = message.lower()
    return any(phrase in text for phrase in (
        "buy a car",
        "buying a car",
        "want a car",
        "need a car",
        "looking for a car",
        "help me find a car",
        "show me cars",
        "show cars",
    ))


def _ready_to_search(constraints: dict) -> bool:
    """Avoid a catalogue dump while still honoring genuinely specific requests."""
    if constraints.get("model"):
        return True
    has_budget = bool(
        constraints.get("max_price_kes") or constraints.get("min_price_kes")
    )
    # A concrete ceiling is enough to produce a useful, deliberately short shortlist.
    # A make/body preference without either a model or budget is still too broad.
    return has_budget


def _ask_for_next_preference(
    state: GraphState, deps: Deps, emit: Emit, constraints: dict
) -> None:
    """Have the LLM ask one orchestrator-selected, high-value question."""
    sid = state["session_id"]
    name = state.get("username", "").split()[0].title()

    has_vehicle_preference = bool(
        constraints.get("make")
        or constraints.get("model")
        or constraints.get("body_types")
        or constraints.get("use_case")
    )
    has_budget = bool(
        constraints.get("max_price_kes") or constraints.get("min_price_kes")
    )

    if not has_vehicle_preference:
        question_goal = (
            "Ask what they will mainly use the car for, with brief examples such as "
            "family trips, city commuting, or business."
        )
        step = "use_case"
    elif not has_budget and not constraints.get("model"):
        question_goal = "Ask for their maximum budget in KES."
        step = "budget"
    else:
        question_goal = (
            "Ask whether they prefer a make or body style, or want you to choose "
            "the strongest options within the stated budget."
        )
        step = "vehicle_preference"

    deps.sessions.update_state(
        sid,
        active_journey="buying",
        awaiting_buy_criteria=True,
        buy_intake_step=step,
        search_constraints=constraints,
    )
    emit(Trace(
        kind="routing",
        label="discovery_intake",
        detail={"step": step, "collected": sorted(constraints)},
    ))
    intake_context = (
        f"User first name: {name or 'not supplied'}.\n"
        f"Collected preferences: {constraints or 'none yet'}.\n"
        f"question_goal: {question_goal}"
    )
    _stream_prose(
        state,
        deps,
        emit,
        prompt_name="discovery_intake.v1",
        user_context=intake_context,
    )


def _is_detail_request(message: str) -> bool:
    text = message.lower()
    return any(phrase in text for phrase in (
        "tell me more", "more about", "what about", "show details",
        "show me details", "details about", "view the",
    ))


def _resolve_displayed_car(state: GraphState, deps: Deps):
    """Resolve a follow-up against rows previously rendered in this session."""
    sid = state["session_id"]
    displayed = deps.sessions.get_state(sid).get("displayed_used_car_ids", [])
    if not displayed:
        return None
    with deps.db_factory() as db:
        cars = tools.compare_cars(db, displayed)

    text = state["message"].lower()
    ordinal_indexes = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
        "fourth": 3, "4th": 3,
    }
    for label, index in ordinal_indexes.items():
        if re.search(rf"\b{re.escape(label)}\b", text) and index < len(cars):
            return cars[index]
    if "cheapest" in text or "most affordable" in text:
        return min(cars, key=lambda item: item.price_kes)
    if "most expensive" in text:
        return max(cars, key=lambda item: item.price_kes)

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    requested_year = int(year_match.group(1)) if year_match else None
    candidates = [
        car for car in cars
        if (requested_year is None or car.year == requested_year)
        and (car.make.lower() in text or car.model.lower() in text)
    ]
    if len(candidates) == 1:
        return candidates[0]

    # A unique year is enough when the user says e.g. "what about the 2017 one?"
    if requested_year is not None:
        year_candidates = [car for car in cars if car.year == requested_year]
        if len(year_candidates) == 1:
            return year_candidates[0]

    # Pronouns and generic detail requests refer to the explicitly focused row.
    context = deps.sessions.get_state(sid)
    focused_id = context.get("focused_entity_id") or context.get("focused_listing_id")
    if focused_id and focused_id in displayed:
        return next((car for car in cars if car.id == focused_id), None)
    return None


def _stream_prose(
    state: GraphState, deps: Deps, emit: Emit, *, prompt_name: str, user_context: str
) -> None:
    system, version = load_prompt(prompt_name)
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": version}))
    for chunk in deps.llm.stream_text(
        system=system, user=prompt_context(state, user_context), max_tokens=400
    ):
        emit(TextDelta(text=chunk))


def _emit_car_suggestions(car, sid: str, deps: Deps, emit: Emit) -> None:
    displayed_ids = deps.sessions.get_state(sid).get("displayed_used_car_ids", [])
    with deps.db_factory() as db:
        displayed_cars = tools.compare_cars(db, displayed_ids)
    emit(suggestions.for_car(
        car,
        displayed_ids,
        displayed_cars=displayed_cars,
    ))


def _emit_vehicle_detail(
    state: GraphState, deps: Deps, emit: Emit, car
) -> None:
    """Select and answer against explicit, allow-listed facts for one DB row."""
    emit(ToolStarted(
        name="select_vehicle_facts",
        params={"car_id": car.id, "question": state["message"]},
    ))
    t0 = time.time()
    fields = tools.select_vehicle_fact_fields(state["message"], deps.llm)
    facts = tools.vehicle_facts(car, fields)
    emit(ToolCompleted(
        name="select_vehicle_facts",
        ms=int((time.time() - t0) * 1000),
        detail={"car_id": car.id, "fields": fields},
    ))
    emit(Trace(
        kind="tool",
        label="vehicle_fact_selection",
        detail={"car_id": car.id, "fields": fields},
    ))
    emit(ComponentReady(type="vehicle_detail", props={
        "car": tools.car_to_props(car, include_gallery=True),
        "facts": facts,
        "image_urls": car.image_urls,
    }))
    _stream_prose(
        state,
        deps,
        emit,
        prompt_name="discovery_detail.v1",
        user_context=tools.vehicle_facts_context(car, fields),
    )


def handle_search(state: GraphState, deps: Deps, emit: Emit) -> None:
    ent = state.get("entities", {})
    sid = state["session_id"]
    session_context = deps.sessions.get_state(sid)

    if ent.get("journey_start"):
        _ask_for_next_preference(state, deps, emit, {})
        return

    if ent.get("car_id"):
        emit(ToolStarted(name="get_used_car", params={"car_id": ent["car_id"]}))
        t0 = time.time()
        with deps.db_factory() as db:
            car = repo.get_used_car(db, ent["car_id"])
        emit(ToolCompleted(
            name="get_used_car",
            ms=int((time.time() - t0) * 1000),
            detail={"car_id": car.id if car else None},
        ))
        if car is None:
            emit(TextDelta(text="That car is no longer available."))
            return
        deps.sessions.update_state(
            sid,
            focused_listing_id=car.id,
            focused_entity_type="used_car",
            focused_entity_id=car.id,
        )
        _emit_vehicle_detail(state, deps, emit, car)
        _emit_car_suggestions(car, sid, deps, emit)
        return

    if _is_detail_request(state["message"]) or (
        tools.is_vehicle_fact_question(state["message"])
        and not _search_constraints(ent)
        and not ent.get("remove_constraints")
        and session_context.get("focused_entity_type") == "used_car"
    ):
        emit(ToolStarted(name="get_displayed_car", params={"reference": state["message"]}))
        t0 = time.time()
        car = _resolve_displayed_car(state, deps)
        emit(ToolCompleted(
            name="get_displayed_car",
            ms=int((time.time() - t0) * 1000),
            detail={"car_id": car.id if car else None},
        ))
        if car is not None:
            deps.sessions.update_state(
                sid,
                focused_listing_id=car.id,
                focused_entity_type="used_car",
                focused_entity_id=car.id,
            )
            _emit_vehicle_detail(state, deps, emit, car)
            _emit_car_suggestions(car, sid, deps, emit)
            return

    previous_constraints = session_context.get("search_constraints", {})
    inherit_previous = bool(previous_constraints) and not _starts_new_search(
        state["message"]
    )
    constraints = (
        dict(previous_constraints) if inherit_previous else {}
    ) | _search_constraints(ent)
    for key in ent.get("remove_constraints", []):
        constraints.pop(key, None)

    if _is_broad_buy_request(state["message"], ent):
        _ask_for_next_preference(state, deps, emit, {})
        return

    if not _ready_to_search(constraints):
        _ask_for_next_preference(state, deps, emit, constraints)
        return

    emit(ToolStarted(name="search_cars", params=constraints))
    deps.sessions.update_state(
        sid,
        awaiting_buy_criteria=False,
        buy_intake_step=None,
    )
    t0 = time.time()
    with deps.db_factory() as db:
        cars = tools.search_cars(
            db,
            make=constraints.get("make"),
            model=constraints.get("model"),
            max_price_kes=constraints.get("max_price_kes"),
            min_price_kes=constraints.get("min_price_kes"),
            max_mileage_km=constraints.get("max_mileage_km"),
            min_mileage_km=constraints.get("min_mileage_km"),
            min_year=constraints.get("min_year"),
            max_year=constraints.get("max_year"),
            body_types=constraints.get("body_types"),
            transmission=constraints.get("transmission"),
            fuel=constraints.get("fuel"),
            location=constraints.get("location"),
            sort_by=constraints.get("sort_by"),
        )
    emit(ToolCompleted(name="search_cars", ms=int((time.time() - t0) * 1000),
                       detail={"count": len(cars)}))

    ids = [c.id for c in cars]
    deps.sessions.update_state(
        sid,
        displayed_used_car_ids=ids,
        focused_listing_id=ids[0] if ids else None,
        focused_entity_type="used_car" if ids else None,
        focused_entity_id=ids[0] if ids else None,
        search_constraints=constraints,
    )

    if not cars:
        emit(TextDelta(text="I couldn't find any cars matching that. Try widening the "
                            "budget or another model."))
        return

    emit(ComponentReady(type="car_card_list",
                        props={"cars": [tools.car_to_props(c) for c in cars]}))
    cheapest = min(cars, key=lambda c: c.price_kes)
    lowest_mileage = min(cars, key=lambda c: c.mileage_km)
    newest = max(cars, key=lambda c: c.year)
    ctx = (
        f"User's applied search constraints: {constraints}.\n"
        f"Found {len(cars)} matching cars after database filtering.\n"
        f"Lowest price: {cheapest.year} {cheapest.make} {cheapest.model}, "
        f"KES {cheapest.price_kes:,}, {cheapest.mileage_km:,} km.\n"
        f"Lowest mileage: {lowest_mileage.year} {lowest_mileage.make} "
        f"{lowest_mileage.model}, KES {lowest_mileage.price_kes:,}, "
        f"{lowest_mileage.mileage_km:,} km.\n"
        f"Newest: {newest.year} {newest.make} {newest.model}, "
        f"KES {newest.price_kes:,}, {newest.mileage_km:,} km."
    )
    _stream_prose(state, deps, emit, prompt_name="discovery.v1", user_context=ctx)
    followups = suggestions.for_car_list(cars)
    if followups:
        emit(followups)


def _resolve_compare_ids(state: GraphState, deps: Deps) -> list[str]:
    explicit = state.get("entities", {}).get("car_ids")
    if explicit:
        return explicit
    sid = state["session_id"]
    context = deps.sessions.get_state(sid)
    displayed = context.get("displayed_used_car_ids", [])
    with deps.db_factory() as db:
        cars = tools.compare_cars(db, displayed)
    by_id = {car.id: car for car in cars}
    text = state["message"].lower()

    # Resolve explicit vehicle references against the rows actually rendered in this
    # session. A year plus make/model uniquely identifies examples such as
    # "the 2016 Mazda Demio" without letting the LLM invent a database id.
    mentioned: list[str] = []
    years = {int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)}
    for car in cars:
        make_hit = car.make.lower() in text
        model_hit = car.model.lower() in text
        year_hit = car.year in years
        if (
            (years and year_hit and (make_hit or model_hit))
            or (not years and make_hit and model_hit)
        ):
            mentioned.append(car.id)

    # Resolve ordinal references in both word and numeric form. Numeric ordinals are
    # only accepted after relational words so years/prices cannot become list indexes.
    ordinal_ids: list[str] = []
    word_ordinals = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
        "fourth": 3, "4th": 3,
        "fifth": 4, "5th": 4,
    }
    for label, index in word_ordinals.items():
        if re.search(rf"\b{re.escape(label)}\b", text) and index < len(displayed):
            ordinal_ids.append(displayed[index])
    for match in re.finditer(
        r"\b(?:against|with|to|versus|vs)\s+(?:the\s+)?(?:number\s+|#)?(\d{1,2})"
        r"(?:st|nd|rd|th)?\b",
        text,
    ):
        index = int(match.group(1)) - 1
        if 0 <= index < len(displayed):
            ordinal_ids.append(displayed[index])

    superlative_ids: list[str] = []
    if "two most expensive" in text:
        superlative_ids.extend(
            car.id for car in sorted(cars, key=lambda item: item.price_kes, reverse=True)[:2]
        )
    else:
        if "cheapest" in text or "most affordable" in text:
            superlative_ids.append(min(cars, key=lambda item: item.price_kes).id)
        if "most expensive" in text:
            superlative_ids.append(max(cars, key=lambda item: item.price_kes).id)
    if "lowest mileage" in text:
        superlative_ids.append(min(cars, key=lambda item: item.mileage_km).id)
    if "newest" in text or "latest" in text:
        superlative_ids.append(max(cars, key=lambda item: item.year).id)
    if "oldest" in text:
        superlative_ids.append(min(cars, key=lambda item: item.year).id)

    resolved = list(dict.fromkeys([*mentioned, *ordinal_ids, *superlative_ids]))
    focused = context.get("focused_listing_id")

    if len(resolved) >= 2:
        return resolved[:2]
    if len(resolved) == 1:
        target = resolved[0]
        if focused and focused != target and focused in by_id:
            # "How does this compare to X?" keeps the current car as the anchor.
            if re.search(r"\b(this|it|current)\b", text):
                return [focused, target]
            return [target, focused]
        previous = context.get("comparison_car_ids", [])
        prior_other = next((item for item in previous if item != target), None)
        if prior_other:
            return [target, prior_other]

    ordinal = state.get("entities", {}).get("ordinal")
    if ordinal == "first_two":
        return displayed[:2]
    if ordinal == "first":
        return displayed[:1]
    if ordinal == "second":
        return displayed[1:2]

    # A generic "another" advances from the current comparison instead of replaying
    # the first two results forever.
    previous = context.get("comparison_car_ids", [])
    anchor = context.get("comparison_anchor_id") or focused
    if "another" in text and anchor:
        candidate = next(
            (item for item in displayed if item != anchor and item not in previous),
            None,
        )
        if candidate:
            return [anchor, candidate]
    return displayed[:2]


def handle_compare(state: GraphState, deps: Deps, emit: Emit) -> None:
    ids = _resolve_compare_ids(state, deps)
    emit(Trace(kind="routing", label="ordinal_resolution",
               detail={"resolved_car_ids": ids}))
    if len(ids) < 2:
        emit(TextDelta(text="I need at least two cars on screen to compare. Search for "
                            "some cars first, then ask me to compare them."))
        return
    emit(ToolStarted(name="compare_cars", params={"car_ids": ids}))
    t0 = time.time()
    with deps.db_factory() as db:
        cars = tools.compare_cars(db, ids)
    emit(ToolCompleted(name="compare_cars", ms=int((time.time() - t0) * 1000),
                       detail={"count": len(cars)}))
    if len(cars) < 2:
        emit(TextDelta(text="I couldn't load both cars to compare."))
        return
    sid = state["session_id"]
    deps.sessions.update_state(
        sid,
        selected_car_ids=[car.id for car in cars],
        comparison_car_ids=[car.id for car in cars],
        comparison_anchor_id=cars[0].id,
        focused_listing_id=cars[0].id,
        focused_entity_type="used_car",
        focused_entity_id=cars[0].id,
    )
    comparison_groups = [
        "identity", "price", "mileage", "transmission", "body", "condition", "location"
    ]
    if tools.is_vehicle_fact_question(state["message"]):
        comparison_groups.extend(
            tools.select_vehicle_fact_fields(state["message"], deps.llm)
        )
    comparison_groups = list(dict.fromkeys(comparison_groups))
    emit(ComponentReady(type="comparison_table", props={
        "cars": [tools.car_to_props(c) for c in cars],
        "fact_groups": comparison_groups,
    }))
    a, b = cars[0], cars[1]
    cheaper = a if a.price_kes <= b.price_kes else b
    newer = a if a.year >= b.year else b
    lower_mileage = a if a.mileage_km <= b.mileage_km else b
    price_gap = abs(a.price_kes - b.price_kes)
    year_gap = abs(a.year - b.year)
    mileage_gap = abs(a.mileage_km - b.mileage_km)
    tradeoffs = (
        [
            f"the {cheaper.year} {cheaper.make} {cheaper.model} costs "
            f"KES {price_gap:,} less"
        ]
        if price_gap
        else ["both have the same asking price"]
    )
    if year_gap:
        tradeoffs.append(
            f"the {newer.year} {newer.make} {newer.model} is {year_gap} "
            f"year{'s' if year_gap != 1 else ''} newer"
        )
    if mileage_gap:
        tradeoffs.append(
            f"the {lower_mileage.year} {lower_mileage.make} {lower_mileage.model} "
            f"has {mileage_gap:,} fewer kilometres"
        )
    comparison_context = json.dumps({
        "requested_fact_groups": comparison_groups,
        "cars": [
            {"id": car.id, "facts": tools.vehicle_facts(car, comparison_groups)}
            for car in cars
        ],
        "deterministic_tradeoffs": tradeoffs,
    }, ensure_ascii=False)
    _stream_prose(
        state,
        deps,
        emit,
        prompt_name="discovery_compare.v1",
        user_context=comparison_context,
    )
    context = deps.sessions.get_state(sid)
    displayed_ids = context.get("displayed_used_car_ids", [])
    with deps.db_factory() as db:
        displayed_cars = tools.compare_cars(db, displayed_ids)
    emit(suggestions.for_car(
        cars[0],
        displayed_ids,
        displayed_cars=displayed_cars,
        exclude_ids=[car.id for car in cars],
    ))


def handle_verdict(state: GraphState, deps: Deps, emit: Emit) -> None:
    sid = state["session_id"]
    car_id = state.get("entities", {}).get("car_id") or \
        deps.sessions.get_state(sid).get("focused_listing_id")
    with deps.db_factory() as db:
        car = tools.compare_cars(db, [car_id])[0] if car_id else None
        if car is None:
            displayed = deps.sessions.get_state(sid).get("displayed_used_car_ids", [])
            car = tools.compare_cars(db, displayed[:1])[0] if displayed else None
        if car is None:
            emit(TextDelta(text="Show me a car first and I'll tell you if the price is fair."))
            return
        emit(ToolStarted(name="price_verdict", params={"car_id": car.id}))
        t0 = time.time()
        verdict = tools.price_verdict(db, car)
    emit(ToolCompleted(name="price_verdict", ms=int((time.time() - t0) * 1000),
                       detail={"verdict": verdict["verdict"],
                               "evidence_count": len(verdict["evidence"])}))
    deps.sessions.update_state(
        sid,
        focused_listing_id=car.id,
        focused_entity_type="used_car",
        focused_entity_id=car.id,
    )
    emit(ComponentReady(type="price_verdict", props={
        "car": tools.car_to_props(car),
        **verdict,
    }))
    verdict_context = (
        f"Selected listing: ID {car.id}; {car.year} {car.make} {car.model}; "
        f"asking price KES {car.price_kes:,}; mileage {car.mileage_km:,} km.\n"
        f"Deterministic verdict: {verdict}"
    )
    _stream_prose(
        state,
        deps,
        emit,
        prompt_name="discovery_verdict.v1",
        user_context=verdict_context,
    )
    emit(suggestions.after_verdict(car.id))


def handle_auctions(state: GraphState, deps: Deps, emit: Emit) -> None:
    sid = state["session_id"]
    auction_id = state.get("entities", {}).get("auction_id")
    emit(ToolStarted(
        name="get_auction" if auction_id else "list_auctions",
        params={"auction_id": auction_id} if auction_id else {},
    ))
    t0 = time.time()
    with deps.db_factory() as db:
        if auction_id:
            selected = repo.get_auction(db, auction_id)
            auctions = [selected] if selected else []
        else:
            auctions = repo.list_auctions(db)
    emit(ToolCompleted(name="get_auction" if auction_id else "list_auctions",
                       ms=int((time.time() - t0) * 1000),
                       detail={"count": len(auctions)}))
    if not auctions:
        emit(TextDelta(text="That auction is no longer available."))
        return
    ids = [a.id for a in auctions]
    changes = {
        "focused_entity_type": "auction",
        "focused_entity_id": ids[0],
    }
    if not auction_id:
        changes["displayed_auction_ids"] = ids
    deps.sessions.update_state(sid, **changes)
    emit(ComponentReady(type="auction_countdown",
                        props={"auctions": [tools.auction_to_props(a) for a in auctions]}))
    auction_context = (
        f"Live auction count: {len(auctions)}.\n"
        + "\n".join(
            f"- ID {auction.id}: {auction.year} {auction.make} {auction.model}; "
            f"current bid KES {auction.current_bid_kes:,}; minimum increment "
            f"KES {auction.min_increment_kes:,}; ends at {auction.ends_at.isoformat()}"
            for auction in auctions
        )
    )
    _stream_prose(
        state,
        deps,
        emit,
        prompt_name="discovery_auctions.v1",
        user_context=auction_context,
    )
    followups = suggestions.for_auctions(auctions)
    if followups:
        emit(followups)
