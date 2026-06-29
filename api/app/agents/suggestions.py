"""Deterministic, executable follow-up suggestions.

Every action comes from a small allow-listed catalogue and references entities already
validated/rendered in the current session.
"""
from __future__ import annotations

from .events import ComponentReady


def component(items: list[dict]) -> ComponentReady | None:
    if not items:
        return None
    return ComponentReady(type="follow_up_suggestions", props={"suggestions": items[:4]})


def for_car_list(cars) -> ComponentReady | None:
    items: list[dict] = []
    if len(cars) >= 2:
        items.append({
            "id": "compare-first-two",
            "label": "Compare the first two",
            "action": {
                "type": "compare_cars",
                "entity_ids": [cars[0].id, cars[1].id],
            },
        })
    if cars:
        cheapest = min(cars, key=lambda car: car.price_kes)
        items.append({
            "id": "view-cheapest",
            "label": f"Tell me more about the {cheapest.year} {cheapest.model}",
            "action": {"type": "select_car", "entity_id": cheapest.id},
        })
    return component(items)


def for_car(
    car,
    displayed_ids: list[str],
    *,
    displayed_cars: list | None = None,
    exclude_ids: list[str] | None = None,
) -> ComponentReady:
    items = [
        {
            "id": f"verdict-{car.id}",
            "label": "Is this price fair?",
            "action": {"type": "price_verdict", "entity_id": car.id},
        },
        {
            "id": f"finance-{car.id}",
            "label": "Calculate financing",
            "action": {"type": "calculate_financing", "entity_id": car.id},
        },
    ]
    excluded = {car.id, *(exclude_ids or [])}
    alternatives = [entity_id for entity_id in displayed_ids if entity_id not in excluded]
    cars_by_id = {item.id: item for item in (displayed_cars or [])}
    for alternative_id in alternatives[:2]:
        alternative = cars_by_id.get(alternative_id)
        label = (
            f"Compare with the {alternative.year} {alternative.make} {alternative.model}"
            if alternative
            else "Compare with another result"
        )
        items.append({
            "id": f"compare-{car.id}-{alternative_id}",
            "label": label,
            "action": {
                "type": "compare_cars",
                "entity_ids": [car.id, alternative_id],
            },
        })
    return component(items)


def after_verdict(car_id: str) -> ComponentReady:
    return component([
        {
            "id": f"finance-after-verdict-{car_id}",
            "label": "Calculate financing",
            "action": {"type": "calculate_financing", "entity_id": car_id},
        },
    ])


def after_financing(car_id: str) -> ComponentReady:
    return component([
        {
            "id": f"verdict-after-financing-{car_id}",
            "label": "Check whether the price is fair",
            "action": {"type": "price_verdict", "entity_id": car_id},
        },
    ])


def after_knowledge(query: str) -> ComponentReady | None:
    if "auction" not in query.lower():
        return None
    return component([
        {
            "id": "browse-auctions",
            "label": "Browse live auctions",
            "action": {"type": "browse_auctions"},
        },
    ])


def for_auctions(auctions) -> ComponentReady | None:
    if not auctions:
        return None
    first = auctions[0]
    return component([
        {
            "id": f"bid-{first.id}",
            "label": f"Bid on the {first.year} {first.model}",
            "action": {"type": "start_bid", "entity_id": first.id},
        },
        {
            "id": "how-auctions-work",
            "label": "How do auctions work?",
            "action": {"type": "ask_knowledge", "topic": "How do CarDuka auctions work?"},
        },
    ])
