"""Router: LLM intent classification with a deterministic fallback so routing never
dead-ends on a model miss."""
from __future__ import annotations

import json
import re

from ..prompts import load_prompt
from .deps import Deps

_VALID_INTENTS = {
    "discovery.search",
    "discovery.compare",
    "discovery.verdict",
    "discovery.auctions",
    "transaction.financing",
    "transaction.bid",
    "rag.knowledge",
    "profile.summary",
    "listings.sell",
}

# Informational phrasing markers + the domains the knowledge base covers. Used so
# "How do I sell a car?" / "How does vehicle insurance work?" route to RAG, while
# "I want to sell my car" routes to the Listings agent (handled after this branch).
_KB_DOMAIN = ("auction", "finance", "financ", "trade-in", "trade in", "insurance",
              "insure", "dealer", "dealership", "sell", "work", "eligib")

_KNOWN_MODELS = ["forester", "fielder", "premio", "note", "lexus lx", " lx", "axio",
                 "vitara", "demio", "x-trail", "harrier"]
_KNOWN_MAKES = ["subaru", "toyota", "nissan", "lexus", "suzuki", "mazda"]


def _authoritative_intent(message: str) -> str | None:
    """Resolve explicit sell-vs-information language without trusting the LLM.

    A model can return a syntactically valid but semantically wrong intent. These
    phrases control whether we start a persistent listing draft, so deterministic
    routing must win for them rather than acting only as an invalid-output fallback.
    """
    t = message.lower()
    has_how = re.search(r"\bhow\b", t) is not None
    is_info = has_how or any(p in t for p in ("what is", "explain", "tell me about"))
    if is_info and any(w in t for w in _KB_DOMAIN):
        return "rag.knowledge"
    if (re.search(r"\bsell", t) and not is_info) or "list my car" in t \
            or "put my car up for sale" in t:
        return "listings.sell"
    return None


def _heuristic_intent(message: str) -> str:
    t = message.lower()
    # 1) Profile / greeting — must precede the bid and financing checks so that
    #    "show me my active bids" and "hi, what can you do" don't mis-route.
    if any(p in t for p in ("my bid", "active bid", "my saved", "saved car",
                            "my history", "my profile", "what can you do")):
        return "profile.summary"
    if re.match(r"\s*(hi|hey|hello|good morning|good afternoon)\b", t):
        return "profile.summary"
    # 2) Compare
    if "compare" in t:
        return "discovery.compare"
    # 3) Price verdict
    if any(w in t for w in ("fair", "worth it", "overpriced", "good price",
                            "price right", "verdict")):
        return "discovery.verdict"
    # 4) Knowledge — informational phrasing about a covered domain. MUST precede the
    #    actionable-sell branch so "how do I sell a car?" is a question, not a draft.
    #    Word-boundary "how" so "show" doesn't false-match.
    authoritative = _authoritative_intent(message)
    if authoritative == "rag.knowledge" or "eligib" in t:
        return "rag.knowledge"
    if any(w in t for w in ("trade-in", "trade in", "policy", "inspection",
                            "return window")):
        return "rag.knowledge"
    # 5) Actionable sell (intent to list a car) — after knowledge so questions go to RAG.
    if authoritative == "listings.sell":
        return "listings.sell"
    # 6) Bid
    if "bid" in t:
        return "transaction.bid"
    # 6) Financing calculation
    if any(w in t for w in ("financ", "loan", "monthly", "instal", "repay")):
        return "transaction.financing"
    # 7) Auctions
    if "auction" in t:
        return "discovery.auctions"
    # 8) Search (default)
    if any(w in t for w in ("find", "search", "show", "looking", "want", "under",
                            "budget", "below")) or any(m in t for m in _KNOWN_MODELS):
        return "discovery.search"
    return "discovery.search"


def _parse_price(message: str) -> int | None:
    """Parse '2.5M', 'KES 2,500,000', '1.8m', '2500000' to integer KES."""
    t = message.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*m\b", t)
    if m:
        return int(float(m.group(1)) * 1_000_000)
    m = re.search(r"(\d[\d]{5,})", t)
    if m:
        return int(m.group(1))
    return None


def _heuristic_entities(message: str, intent: str) -> dict:
    t = message.lower()
    entities: dict = {}
    for make in _KNOWN_MAKES:
        if make in t:
            entities["make"] = make.title()
            break
    for model in _KNOWN_MODELS:
        name = model.strip()
        if name and name in t:
            entities["model"] = "LX" if name in ("lx", "lexus lx") else name.title()
            break
    price = _parse_price(message)
    if price is not None:
        if intent == "transaction.bid":
            entities["amount_kes"] = price
        elif any(w in t for w in ("under", "below", "less than", "max", "up to", "budget")):
            entities["max_price_kes"] = price
        elif any(w in t for w in ("over", "above", "more than", "min")):
            entities["min_price_kes"] = price
        else:
            entities["max_price_kes"] = price
    if "first two" in t or "both" in t:
        entities["ordinal"] = "first_two"
    elif "first" in t:
        entities["ordinal"] = "first"
    elif "second" in t:
        entities["ordinal"] = "second"
    return entities


def classify(message: str, deps: Deps, context: dict | None = None) -> tuple[str, dict, str]:
    """Return (intent, entities, prompt_version). Deterministic fallback on LLM miss."""
    system, version = load_prompt("router.v1")
    intent = ""
    entities: dict = {}
    try:
        llm_input = message
        if context:
            llm_input = json.dumps({
                "latest_user_message": message,
                "conversation_context": context,
            })
        result = deps.llm.complete_json(system=system, user=llm_input, max_tokens=256)
        intent = str(result.get("intent", "")).strip()
        ent = result.get("entities")
        if isinstance(ent, dict):
            entities = ent
    except Exception:
        intent = ""

    # Explicit informational/actionable sell phrasing is authoritative. The LLM may
    # return another *valid* intent, which would otherwise bypass the fallback.
    authoritative = _authoritative_intent(message)
    if authoritative is not None:
        intent = authoritative
    elif intent not in _VALID_INTENTS:
        intent = _heuristic_intent(message)
    # Always merge deterministic entity parsing (numbers/models) — the heuristic
    # extractor is reliable and protects against sparse LLM output.
    merged = _heuristic_entities(message, intent)
    merged.update({k: v for k, v in entities.items() if v not in (None, "", [])})
    return intent, merged, version
