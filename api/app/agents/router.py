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
              "insure", "cover", "premium", "dealer", "dealership", "sell",
              "swap", "exchange", "inspection", "return", "payment", "logbook",
              "escrow", "work", "eligib")

_KNOWN_MODELS = ["forester", "fielder", "premio", "note", "lexus lx", " lx", "axio",
                 "vitara", "demio", "x-trail", "harrier"]
_KNOWN_MAKES = ["subaru", "toyota", "nissan", "lexus", "suzuki", "mazda"]
_KNOWN_BODY_TYPES = {
    "suv": ["SUV"],
    "station wagon": ["Station Wagon"],
    "wagon": ["Station Wagon"],
    "hatchback": ["Hatchback"],
    "sedan": ["Sedan"],
    "pickup": ["Pickup"],
    "pick-up": ["Pickup"],
}

_INTEGER_ENTITIES = {
    "max_price_kes", "min_price_kes", "max_mileage_km", "min_mileage_km",
    "min_year", "max_year", "amount_kes", "principal_kes", "deposit_kes",
    "term_months",
}


def _normalize_entities(entities: dict) -> dict:
    """Type and allow-list model output before it can reach deterministic tools."""
    if not isinstance(entities, dict):
        return {}
    out: dict = {}
    for key in (
        "make", "model", "location", "use_case", "ordinal", "auction_id", "car_id"
    ):
        value = entities.get(key)
        if isinstance(value, str) and 0 < len(value.strip()) <= 100:
            out[key] = value.strip()
    for key in _INTEGER_ENTITIES:
        value = entities.get(key)
        if value in (None, ""):
            continue
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            continue
        if number > 0:
            out[key] = number
    deposit_pct = entities.get("deposit_pct")
    try:
        if deposit_pct is not None and 0 <= float(deposit_pct) <= 100:
            out["deposit_pct"] = float(deposit_pct)
    except (TypeError, ValueError):
        pass
    body_types = entities.get("body_types")
    if isinstance(body_types, str):
        body_types = [body_types]
    if isinstance(body_types, list):
        aliases = {
            "suv": "SUV", "sedan": "Sedan", "hatchback": "Hatchback",
            "station wagon": "Station Wagon", "wagon": "Station Wagon",
            "pickup": "Pickup", "pick-up": "Pickup",
        }
        clean = [
            aliases.get(str(item).strip().lower(), str(item).strip().title())
            for item in body_types if str(item).strip()
        ]
        if clean:
            out["body_types"] = clean[:6]
    transmission = entities.get("transmission")
    if isinstance(transmission, str):
        match = {"automatic": "Automatic", "manual": "Manual"}.get(
            transmission.strip().lower()
        )
        if match:
            out["transmission"] = match
    fuel = entities.get("fuel")
    if isinstance(fuel, str):
        match = {
            "petrol": "Petrol", "diesel": "Diesel", "hybrid": "Hybrid",
            "electric": "Electric",
        }.get(fuel.strip().lower())
        if match:
            out["fuel"] = match
    sort_by = entities.get("sort_by")
    if sort_by in {"price_asc", "mileage_asc", "year_desc"}:
        out["sort_by"] = sort_by
    car_ids = entities.get("car_ids")
    if isinstance(car_ids, list):
        out["car_ids"] = [str(item) for item in car_ids if item][:4]
    return out


def _authoritative_intent(message: str) -> str | None:
    """Resolve explicit sell-vs-information language without trusting the LLM.

    A model can return a syntactically valid but semantically wrong intent. These
    phrases control whether we start a persistent listing draft, so deterministic
    routing must win for them rather than acting only as an invalid-output fallback.
    """
    t = message.lower()
    has_how = re.search(r"\bhow\b", t) is not None
    alias_question = (
        re.match(r"\s*(what|which|can|does|do|are|is)\b", t) is not None
        and any(term in t for term in (
            "cover", "premium", "dealer", "dealership", "trade", "swap",
            "exchange", "inspection", "return", "payment", "logbook", "escrow",
        ))
    )
    is_info = has_how or any(p in t for p in ("what is", "explain", "tell me about")) \
        or alias_question
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


def _money_mentions(message: str) -> list[int]:
    """Extract KES-like amounts while excluding mileage/year measurements."""
    text = message.lower().replace(",", "")
    values: list[int] = []
    pattern = re.compile(
        r"(?:kes\s*)?(\d+(?:\.\d+)?)\s*(million|thousand|m|k)?\b"
    )
    for match in pattern.finditer(text):
        suffix = text[match.end():].lstrip()
        if suffix.startswith(("km", "kms", "kilomet")):
            continue
        raw = float(match.group(1))
        unit = match.group(2)
        if unit in ("million", "m"):
            value = int(raw * 1_000_000)
        elif unit in ("thousand", "k"):
            value = int(raw * 1_000)
        else:
            value = int(raw)
            # Bare small numbers are usually years/counts, not KES amounts.
            if value < 100_000:
                continue
        values.append(value)
    return values


def _numeric_search_entities(message: str) -> dict:
    """Deterministic range parsing protects the DB query from sparse LLM output."""
    text = message.lower().replace(",", "")
    entities: dict = {}

    mileage_matches = re.findall(
        r"(\d{2,7})\s*(?:km|kms|kilometres|kilometers)\b", text
    )
    mileage_values = [int(value) for value in mileage_matches]
    if mileage_values:
        if any(word in text for word in ("under", "below", "less than", "maximum", "max")):
            entities["max_mileage_km"] = max(mileage_values)
        elif any(word in text for word in ("over", "above", "at least", "minimum", "min")):
            entities["min_mileage_km"] = min(mileage_values)
    if any(phrase in text for phrase in ("low mileage", "lowest mileage", "fewer kilometres",
                                          "fewer kilometers")):
        entities["sort_by"] = "mileage_asc"

    amounts = _money_mentions(message)
    if len(amounts) >= 2 and any(word in text for word in ("between", "from", "range")):
        entities["min_price_kes"] = min(amounts[:2])
        entities["max_price_kes"] = max(amounts[:2])
    elif amounts:
        amount = amounts[-1]
        if any(word in text for word in ("over", "above", "more than", "at least", "minimum")):
            entities["min_price_kes"] = amount
        else:
            entities["max_price_kes"] = amount

    years = [int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if len(years) >= 2 and any(word in text for word in ("between", "from", "range")):
        entities["min_year"] = min(years[:2])
        entities["max_year"] = max(years[:2])
    elif years:
        if any(word in text for word in ("newer than", "after", "from", "at least")):
            entities["min_year"] = years[0]
        elif any(word in text for word in ("older than", "before", "up to")):
            entities["max_year"] = years[0]
    if any(phrase in text for phrase in ("newest", "latest model", "most recent")):
        entities["sort_by"] = "year_desc"
    elif any(phrase in text for phrase in ("cheapest", "lowest price", "most affordable")):
        entities["sort_by"] = "price_asc"
    return entities


def _financing_entities(message: str) -> dict:
    """Parse financing numbers in their own semantic domains.

    Words such as "over 36 months" describe a term and must never affect price
    direction. Deterministic parsing wins over model output for these figures.
    """
    text = message.lower().replace(",", "")
    entities: dict = {}
    amounts = _money_mentions(message)
    if amounts:
        entities["principal_kes"] = amounts[0]

    percent = re.search(
        r"(?:put\s+down|deposit(?:\s+of)?|down\s+payment(?:\s+of)?)\s*(\d+(?:\.\d+)?)\s*%",
        text,
    ) or re.search(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:deposit|down|down\s+payment)", text
    )
    if percent:
        entities["deposit_pct"] = float(percent.group(1))

    deposit_amount = re.search(
        r"(?:deposit|put\s+down|down\s+payment)\s+(?:of\s+)?(?:kes\s*)?"
        r"(\d+(?:\.\d+)?)\s*(million|thousand|m|k)?\b",
        text,
    )
    if deposit_amount and not percent:
        raw = float(deposit_amount.group(1))
        unit = deposit_amount.group(2)
        multiplier = 1_000_000 if unit in ("million", "m") else (
            1_000 if unit in ("thousand", "k") else 1
        )
        value = int(raw * multiplier)
        if value >= 1_000:
            entities["deposit_kes"] = value

    term = re.search(r"\b(\d{1,3})\s*(months?|mos?)\b", text)
    if term:
        entities["term_months"] = int(term.group(1))
    else:
        years = re.search(r"\b(\d{1,2})\s*years?\b", text)
        if years:
            entities["term_months"] = int(years.group(1)) * 12
    return entities


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
    for phrase, body_types in _KNOWN_BODY_TYPES.items():
        if re.search(rf"\b{re.escape(phrase)}s?\b", t):
            entities["body_types"] = body_types
            break
    if any(word in t for word in ("family", "kids", "school run", "road trip")):
        entities.setdefault("body_types", ["SUV", "Station Wagon"])
        entities["use_case"] = "family"
    elif any(word in t for word in ("city", "commute", "commuting", "first car")):
        entities.setdefault("body_types", ["Hatchback", "Sedan"])
        entities["use_case"] = "city driving"
    elif any(word in t for word in ("business", "work vehicle", "cargo")):
        entities.setdefault("body_types", ["Station Wagon", "SUV", "Pickup"])
        entities["use_case"] = "business"
    if "manual" in t:
        entities["transmission"] = "Manual"
    elif "automatic" in t or "auto" in t:
        entities["transmission"] = "Automatic"
    for location in ("nairobi", "mombasa", "nakuru", "kiambu", "eldoret", "kisumu"):
        if re.search(rf"\b{location}\b", t):
            entities["location"] = location.title()
            break
    if intent == "discovery.search":
        remove: list[str] = []
        if any(p in t for p in (
            "ignore mileage", "ignore the mileage", "any mileage", "no mileage limit"
        )):
            remove.extend(["min_mileage_km", "max_mileage_km", "sort_by"])
        if any(p in t for p in ("ignore budget", "any budget", "no price limit",
                                "ignore price")):
            remove.extend(["min_price_kes", "max_price_kes"])
        if any(p in t for p in ("any make", "no preferred make", "ignore make")):
            remove.extend(["make", "model"])
        if any(p in t for p in ("any body", "any body type", "ignore body type")):
            remove.extend(["body_types", "use_case"])
        if any(p in t for p in ("any transmission", "ignore transmission")):
            remove.append("transmission")
        if remove:
            entities["remove_constraints"] = list(dict.fromkeys(remove))
    if intent == "transaction.bid":
        price = _parse_price(message)
        if price is not None:
            entities["amount_kes"] = price
    elif intent == "transaction.financing":
        entities.update(_financing_entities(message))
    else:
        entities.update(_numeric_search_entities(message))
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
    merged = _normalize_entities(entities)
    # Deterministic parsing wins for numeric ranges and explicit known facets.
    merged.update(_heuristic_entities(message, intent))
    return intent, merged, version
