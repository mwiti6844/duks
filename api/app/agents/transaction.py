"""Transaction Agent: financing calculator + bid with a human-in-the-loop gate.

The bid path NEVER persists. It validates against financial rules and streams a
signed, expiring proposal as a bid_confirm_modal. Only POST /api/bids/confirm writes.
"""
from __future__ import annotations

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

_KNOWN_AUCTION_MODELS = ["forester", "fielder", "premio", "note", "lx", "harrier",
                         "x-trail", "axio", "vitara"]


def _stream_prose(state: GraphState, deps: Deps, emit: Emit, ctx: str) -> None:
    system, version = load_prompt("transaction.v1")
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": version}))
    for chunk in deps.llm.stream_text(
        system=system, user=prompt_context(state, ctx), max_tokens=300
    ):
        emit(TextDelta(text=chunk))


def handle_financing(state: GraphState, deps: Deps, emit: Emit) -> None:
    sid = state["session_id"]
    ent = state.get("entities", {})
    with deps.db_factory() as db:
        car = None
        context = deps.sessions.get_state(sid)
        focused_car = (
            context.get("focused_entity_id")
            if context.get("focused_entity_type") == "used_car"
            else context.get("focused_listing_id")
        )
        car_id = ent.get("car_id") or focused_car
        if car_id:
            car = repo.get_used_car(db, car_id)
        if car is None:
            displayed = deps.sessions.get_state(sid).get("displayed_used_car_ids", [])
            car = repo.get_used_car(db, displayed[0]) if displayed else None
    principal = ent.get("max_price_kes") or (car.price_kes if car else None)
    if principal is None:
        deps.sessions.update_state(sid, active_journey="financing", awaiting_finance_price=True)
        emit(TextDelta(text=(
            "Which car would you like to finance? Select a car from the marketplace, "
            "or tell me its price in KES so I can calculate a plan."
        )))
        return
    deps.sessions.update_state(sid, awaiting_finance_price=False)

    emit(ToolStarted(name="compute_financing", params={"principal_kes": principal}))
    t0 = time.time()
    plan = tools.compute_financing(principal_kes=principal, deposit_kes=ent.get("deposit_kes"))
    emit(ToolCompleted(name="compute_financing", ms=int((time.time() - t0) * 1000),
                       detail={"monthly_payment_kes": plan["monthly_payment_kes"]}))

    emit(ComponentReady(type="financing_calculator", props={
        "car": tools.car_to_props(car) if car else None,
        **plan,
    }))
    emit(TextDelta(text=""))
    _stream_prose(
        state, deps, emit,
        ctx=(f"Financing computed: price KES {plan['price_kes']:,}, deposit "
             f"KES {plan['deposit_kes']:,}, {plan['term_months']} months at "
             f"{plan['annual_rate_pct']}% — KES {plan['monthly_payment_kes']:,}/month. "
             f"The calculator is interactive so they can adjust deposit and term."),
    )
    if car is not None:
        emit(suggestions.after_financing(car.id))


def _resolve_auction(state: GraphState, deps: Deps):
    """Deterministically resolve the bid target: entity model -> message scan ->
    focused listing -> first displayed auction."""
    sid = state["session_id"]
    ent = state.get("entities", {})
    msg = state.get("message", "").lower()
    with deps.db_factory() as db:
        if ent.get("auction_id"):
            a = repo.get_auction(db, ent["auction_id"])
            if a:
                return a
        if ent.get("model"):
            a = repo.find_auction_by_model(db, ent["model"])
            if a:
                return a
        for name in _KNOWN_AUCTION_MODELS:
            if name in msg:
                a = repo.find_auction_by_model(db, name)
                if a:
                    return a
        context = deps.sessions.get_state(sid)
        focused = (
            context.get("focused_entity_id")
            if context.get("focused_entity_type") == "auction"
            else None
        )
        if focused:
            a = repo.get_auction(db, focused)
            if a:
                return a
        displayed = deps.sessions.get_state(sid).get("displayed_auction_ids", [])
        if displayed:
            return repo.get_auction(db, displayed[0])
    return None


def handle_bid(state: GraphState, deps: Deps, emit: Emit) -> None:
    sid = state["session_id"]
    ent = state.get("entities", {})
    amount = ent.get("amount_kes")
    auction = _resolve_auction(state, deps)
    emit(Trace(kind="routing", label="bid_target",
               detail={"auction_id": auction.id if auction else None,
                       "amount_kes": amount}))
    if auction is None:
        emit(TextDelta(text="Which auction would you like to bid on? Browse the auctions "
                            "first, then tell me the car and amount."))
        return
    if not amount:
        emit(TextDelta(text=f"How much would you like to bid on the {auction.year} "
                            f"{auction.make} {auction.model}? The minimum next bid is "
                            f"KES {auction.current_bid_kes + auction.min_increment_kes:,}."))
        return

    emit(ToolStarted(name="prepare_bid_proposal",
                     params={"auction_id": auction.id, "amount_kes": amount}))
    t0 = time.time()
    try:
        with deps.db_factory() as db:
            result = tools.prepare_bid_proposal(
                db, secret=deps.settings.bid_signing_secret,
                user_id=state["user_id"], auction=auction, amount_kes=amount)
    except tools.BidRuleError as exc:
        emit(ToolCompleted(name="prepare_bid_proposal",
                           ms=int((time.time() - t0) * 1000), detail={"rejected": True}))
        emit(TextDelta(text=str(exc)))
        return
    emit(ToolCompleted(name="prepare_bid_proposal", ms=int((time.time() - t0) * 1000),
                       detail={"meets_reserve": result["meets_reserve"]}))

    # Persist the pending proposal so a page refresh can restore the modal.
    deps.sessions.set_pending_bid(sid, result)

    emit(ComponentReady(type="bid_confirm_modal", props={
        "auction": result["auction"],
        "amount_kes": result["amount_kes"],
        "meets_reserve": result["meets_reserve"],
        "signed_proposal": result["signed_proposal"],
    }))
    _stream_prose(
        state, deps, emit,
        ctx=(f"Prepared a bid of KES {amount:,} on the {auction.year} {auction.make} "
             f"{auction.model}. It is NOT placed yet — the user must confirm in the modal."),
    )
