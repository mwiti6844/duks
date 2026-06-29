"""Typed generative-UI actions.

The browser supplies an action type and entity ID, but the server validates every
reference against authenticated session state and reloads entities from the database.
Visible labels are never authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..db import repositories as repo
from .deps import Deps


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectCarAction(_Action):
    type: Literal["select_car"]
    entity_id: str


class CompareCarsAction(_Action):
    type: Literal["compare_cars"]
    entity_ids: list[str] = Field(min_length=2, max_length=4)


class PriceVerdictAction(_Action):
    type: Literal["price_verdict"]
    entity_id: str


class CalculateFinancingAction(_Action):
    type: Literal["calculate_financing"]
    entity_id: str


class SelectAuctionAction(_Action):
    type: Literal["select_auction"]
    entity_id: str


class StartBidAction(_Action):
    type: Literal["start_bid"]
    entity_id: str


class AskKnowledgeAction(_Action):
    type: Literal["ask_knowledge"]
    topic: str = Field(min_length=1, max_length=300)


class BrowseAuctionsAction(_Action):
    type: Literal["browse_auctions"]


class StartJourneyAction(_Action):
    type: Literal["start_journey"]
    journey: Literal[
        "buy_car",
        "sell_car",
        "finance_car",
        "trade_in",
        "insurance",
        "dealer_finance",
    ]


UIAction = Annotated[
    SelectCarAction
    | CompareCarsAction
    | PriceVerdictAction
    | CalculateFinancingAction
    | SelectAuctionAction
    | StartBidAction
    | AskKnowledgeAction
    | BrowseAuctionsAction
    | StartJourneyAction,
    Field(discriminator="type"),
]


class ActionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedAction:
    intent: str
    entities: dict


def _require_displayed_car(entity_id: str, sid: str, deps: Deps):
    context = deps.sessions.get_state(sid)
    if entity_id not in context.get("displayed_used_car_ids", []):
        raise ActionError("Car is not part of the current displayed results")
    with deps.db_factory() as db:
        car = repo.get_used_car(db, entity_id)
    if car is None:
        raise ActionError("Car no longer exists")
    return car


def _require_displayed_auction(entity_id: str, sid: str, deps: Deps):
    context = deps.sessions.get_state(sid)
    if entity_id not in context.get("displayed_auction_ids", []):
        raise ActionError("Auction is not part of the current displayed results")
    with deps.db_factory() as db:
        auction = repo.get_auction(db, entity_id)
    if auction is None:
        raise ActionError("Auction no longer exists")
    return auction


def resolve_action(action: UIAction, *, sid: str, deps: Deps) -> ResolvedAction:
    if isinstance(action, SelectCarAction):
        car = _require_displayed_car(action.entity_id, sid, deps)
        deps.sessions.update_state(
            sid,
            focused_entity_type="used_car",
            focused_entity_id=car.id,
            focused_listing_id=car.id,
        )
        return ResolvedAction("discovery.search", {"car_id": car.id})

    if isinstance(action, CompareCarsAction):
        if len(set(action.entity_ids)) != len(action.entity_ids):
            raise ActionError("Comparison cars must be distinct")
        for entity_id in action.entity_ids:
            _require_displayed_car(entity_id, sid, deps)
        return ResolvedAction("discovery.compare", {"car_ids": action.entity_ids})

    if isinstance(action, PriceVerdictAction):
        car = _require_displayed_car(action.entity_id, sid, deps)
        deps.sessions.update_state(
            sid,
            focused_entity_type="used_car",
            focused_entity_id=car.id,
            focused_listing_id=car.id,
        )
        return ResolvedAction("discovery.verdict", {"car_id": car.id})

    if isinstance(action, CalculateFinancingAction):
        car = _require_displayed_car(action.entity_id, sid, deps)
        deps.sessions.update_state(
            sid,
            focused_entity_type="used_car",
            focused_entity_id=car.id,
            focused_listing_id=car.id,
        )
        return ResolvedAction("transaction.financing", {"car_id": car.id})

    if isinstance(action, SelectAuctionAction):
        auction = _require_displayed_auction(action.entity_id, sid, deps)
        deps.sessions.update_state(
            sid, focused_entity_type="auction", focused_entity_id=auction.id
        )
        return ResolvedAction("discovery.auctions", {"auction_id": auction.id})

    if isinstance(action, StartBidAction):
        auction = _require_displayed_auction(action.entity_id, sid, deps)
        deps.sessions.update_state(
            sid, focused_entity_type="auction", focused_entity_id=auction.id
        )
        return ResolvedAction("transaction.bid", {"auction_id": auction.id})

    if isinstance(action, AskKnowledgeAction):
        return ResolvedAction("rag.knowledge", {"topic": action.topic})

    if isinstance(action, BrowseAuctionsAction):
        return ResolvedAction("discovery.auctions", {})

    if isinstance(action, StartJourneyAction):
        routes = {
            "buy_car": ResolvedAction("discovery.search", {"journey_start": True}),
            "sell_car": ResolvedAction("listings.sell", {}),
            "finance_car": ResolvedAction("transaction.financing", {"journey_start": True}),
            "trade_in": ResolvedAction(
                "rag.knowledge", {"topic": "How does CarDuka trade-in work?"}
            ),
            "insurance": ResolvedAction(
                "rag.knowledge", {"topic": "How does CarDuka vehicle insurance work?"}
            ),
            "dealer_finance": ResolvedAction(
                "rag.knowledge", {"topic": "How does CarDuka dealership financing work?"}
            ),
        }
        return routes[action.journey]

    raise ActionError("Unsupported action")
