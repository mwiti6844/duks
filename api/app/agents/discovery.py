"""Discovery Agent: search, compare, AI price verdict, browse auctions.

Worker functions emit transport-neutral AgentExecutionEvents via `emit`. Ordinal
references ("compare the first two") resolve from session display state, never the LLM.
"""
from __future__ import annotations

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


def handle_search(state: GraphState, deps: Deps, emit: Emit) -> None:
    ent = state.get("entities", {})
    sid = state["session_id"]

    if ent.get("journey_start"):
        deps.sessions.update_state(
            sid,
            active_journey="buying",
            awaiting_buy_criteria=True,
            search_constraints={},
        )
        memory = state.get("user_memory", {})
        preference = ""
        if memory.get("budget_kes") or memory.get("preferred_makes"):
            preference = (
                " I can also use your saved preferences if you want: "
                f"budget {memory.get('budget_kes') or 'not set'}, "
                f"makes {memory.get('preferred_makes') or 'not set'}."
            )
        emit(TextDelta(text=(
            "What kind of car are you looking for? Tell me a make or model, body type, "
            f"budget, or how you plan to use it.{preference}"
        )))
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
        emit(ComponentReady(type="car_card", props=tools.car_to_props(car)))
        details = (
            f"Selected listing from the database: ID {car.id}; {car.year} "
            f"{car.make} {car.model}; KES {car.price_kes:,}; {car.mileage_km:,} km; "
            f"{car.transmission}; {car.fuel}; {car.condition}; {car.body_type}; "
            f"located in {car.location}."
        )
        if car.description:
            details += f" Description: {car.description}"
        _stream_prose(
            state, deps, emit, prompt_name="discovery_detail.v1", user_context=details
        )
        _emit_car_suggestions(car, sid, deps, emit)
        return

    if _is_detail_request(state["message"]):
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
            emit(ComponentReady(type="car_card", props=tools.car_to_props(car)))
            details = (
                f"Selected listing from the database: ID {car.id}; {car.year} "
                f"{car.make} {car.model}; KES {car.price_kes:,}; "
                f"{car.mileage_km:,} km; {car.transmission}; {car.fuel}; "
                f"{car.condition}; {car.body_type}; located in {car.location}."
            )
            if car.description:
                details += f" Description: {car.description}"
            _stream_prose(
                state, deps, emit, prompt_name="discovery_detail.v1", user_context=details
            )
            _emit_car_suggestions(car, sid, deps, emit)
            return

    emit(ToolStarted(name="search_cars", params=ent))
    deps.sessions.update_state(sid, awaiting_buy_criteria=False)
    t0 = time.time()
    with deps.db_factory() as db:
        cars = tools.search_cars(
            db,
            make=ent.get("make"),
            model=ent.get("model"),
            max_price_kes=ent.get("max_price_kes"),
            min_price_kes=ent.get("min_price_kes"),
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
        search_constraints=ent,
    )

    if not cars:
        emit(TextDelta(text="I couldn't find any cars matching that. Try widening the "
                            "budget or another model."))
        return

    emit(ComponentReady(type="car_card_list",
                        props={"cars": [tools.car_to_props(c) for c in cars]}))
    cheapest = min(cars, key=lambda c: c.price_kes)
    ctx = (f"Found {len(cars)} matching cars. Cheapest: {cheapest.year} "
           f"{cheapest.make} {cheapest.model} at KES {cheapest.price_kes:,}.")
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

    resolved = list(dict.fromkeys([*mentioned, *ordinal_ids]))
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
    emit(ComponentReady(type="comparison_table",
                        props={"cars": [tools.car_to_props(c) for c in cars]}))
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
    emit(TextDelta(
        text="Here's a side-by-side: " + "; ".join(tradeoffs) + "."
    ))
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
    label = {"fair": "fairly priced", "below_market": "priced below the market",
             "above_market": "priced above the market",
             "insufficient_data": "hard to assess"}.get(verdict["verdict"], "assessed")
    emit(TextDelta(text=f"Based on recent comparable sales, this {car.make} "
                        f"{car.model} looks {label}."))
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
    emit(TextDelta(text=f"Here are {len(auctions)} live auctions with countdown timers. "
                        f"Tell me an amount and a car to place a bid."))
    followups = suggestions.for_auctions(auctions)
    if followups:
        emit(followups)
