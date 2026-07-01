"""Non-blocking semantic titles for durable conversation threads."""
from __future__ import annotations

import json
import logging
import re

from .db import repositories as repo
from .db.engine import SessionLocal
from .llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_GENERIC = {
    "help me buy a car",
    "help me finance a car",
    "i want to sell my car",
    "new conversation",
    "car conversation",
    "carduka conversation",
}


def _money(value: int) -> str:
    if value >= 1_000_000:
        amount = value / 1_000_000
        return f"{amount:g}M"
    if value >= 1_000:
        return f"{value // 1_000}K"
    return str(value)


def _fallback_title(context: dict, user_messages: list[str]) -> str:
    intent = context.get("last_intent", "")
    constraints = context.get("search_constraints", {}) or {}
    make = constraints.get("make")
    model = constraints.get("model")
    minimum = constraints.get("min_price_kes")
    maximum = constraints.get("max_price_kes")

    if intent == "listings.sell":
        latest = " ".join(user_messages[-2:])
        vehicle = re.search(
            r"\b((?:19|20)\d{2}\s+)?([A-Z][a-z]+\s+[A-Z][A-Za-z0-9-]+)\b",
            latest,
        )
        return f"Selling {vehicle.group(0).strip()}" if vehicle else "Selling a car"
    if intent == "transaction.financing":
        return f"Financing {make} {model}".strip() if make or model else "Vehicle financing"
    if intent == "transaction.bid":
        return f"{make} {model} auction bid".strip() if make or model else "Vehicle auction bid"
    if intent == "discovery.compare":
        return "Vehicle comparison"
    if intent.startswith("discovery."):
        if make or model:
            return f"{make or ''} {model or ''} search".strip()
        if minimum and maximum:
            return f"Car search · KES {_money(int(minimum))}–{_money(int(maximum))}"
        if maximum:
            return f"Car search · under KES {_money(int(maximum))}"
        return "New car search"
    if intent == "rag.knowledge" and user_messages:
        latest = user_messages[-1].lower()
        for term, title in (
            ("trade", "Understanding CarDuka trade-in"),
            ("insurance", "CarDuka vehicle insurance"),
            ("dealer", "CarDuka dealer financing"),
            ("auction", "How CarDuka auctions work"),
            ("financ", "CarDuka financing questions"),
        ):
            if term in latest:
                return title
        return "CarDuka policies and services"
    return "CarDuka assistant conversation"


def _clean_title(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    title = " ".join(value.replace("\n", " ").strip(" \"'`.:;-").split())
    if not 3 <= len(title) <= 60 or title.lower() in _GENERIC:
        return None
    return title


def refresh_thread_title(thread_id: str, user_id: str, llm: LLMProvider) -> None:
    """Update an unlocked title during the first three user turns."""
    try:
        with SessionLocal() as db:
            thread = repo.get_conversation_thread(
                db, thread_id=thread_id, user_id=user_id
            )
            if thread is None or thread.title_locked:
                return
            user_turns = repo.count_user_messages(
                db, thread_id=thread_id, user_id=user_id
            )
            if user_turns == 0 or user_turns > 3:
                return
            messages = repo.list_conversation_messages(
                db, thread_id=thread_id, user_id=user_id
            ) or []
            user_messages = [
                "".join(
                    block.get("text", "")
                    for block in message.content
                    if block.get("type") == "text"
                )
                for message in messages
                if message.role == "user"
            ][-3:]
            context = json.loads(thread.context_json or "{}")
            fallback = _fallback_title(context, user_messages)

            title = None
            try:
                result = llm.complete_json(
                    system=(
                        "THREAD_TITLE\nGenerate a specific 3-7 word title for this "
                        "CarDuka conversation. Describe the actual task, vehicle, "
                        "comparison, budget, financing, sale, auction, or policy topic. "
                        "Avoid generic titles such as 'Help me buy a car'. Return JSON "
                        'only: {"title":"..."}.'
                    ),
                    user=json.dumps({
                        "conversation_context": context,
                        "recent_user_messages": user_messages,
                        "fallback_hint": fallback,
                    }),
                    max_tokens=60,
                )
                title = _clean_title(result.get("title"))
            except Exception:
                logger.info("LLM thread title generation failed; using fallback", exc_info=True)

            repo.update_conversation_thread(
                db,
                thread_id=thread_id,
                user_id=user_id,
                title=title or fallback,
                title_locked=False,
            )
    except Exception:
        logger.exception("Could not refresh title for thread %s", thread_id)
