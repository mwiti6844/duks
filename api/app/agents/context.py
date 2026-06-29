"""Small, sanitized prompt context assembled from session and durable user memory."""
from __future__ import annotations

import json

from .state import GraphState


def prompt_context(state: GraphState, task_context: str) -> str:
    recent = state.get("recent_history", [])[-8:]
    conversation = state.get("conversation_context", {})
    user_memory = state.get("user_memory", {})
    payload = {
        "task_context": task_context,
        "recent_conversation": recent,
        "active_journey": conversation.get("active_journey"),
        "focused_entity_type": conversation.get("focused_entity_type"),
        "focused_entity_id": conversation.get("focused_entity_id"),
        "confirmed_user_preferences": user_memory,
    }
    return json.dumps(payload, ensure_ascii=False)
