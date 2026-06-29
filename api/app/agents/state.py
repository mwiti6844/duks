"""Typed LangGraph state threaded through the router and worker nodes."""
from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    # Identity / session
    user_id: str
    username: str
    session_id: str
    message: str
    recent_history: list[dict[str, str]]
    conversation_context: dict[str, Any]
    user_memory: dict[str, Any]
    ui_action: dict[str, Any]
    action_intent: str
    action_entities: dict[str, Any]

    # Classification
    intent: str
    entities: dict[str, Any]

    # Deterministic ordinal resolution (tracked separately per the review)
    displayed_used_car_ids: list[str]
    displayed_auction_ids: list[str]
    focused_listing_id: str | None
    selected_car_ids: list[str]
    comparison_car_ids: list[str]
    comparison_anchor_id: str | None

    # Accumulated tool outputs (domain data, not UI)
    tool_results: dict[str, Any]
