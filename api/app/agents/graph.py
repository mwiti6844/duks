"""LangGraph orchestration. The router node classifies intent; conditional edges
dispatch to a worker node. Nodes PUBLISH execution events via LangGraph's stream
writer (custom stream mode) and return state updates — they never emit SSE directly.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from . import discovery, listings, profile, rag, router, transaction
from .deps import Deps
from .events import Trace
from .state import GraphState

# intent -> worker node name
_INTENT_NODE = {
    "discovery.search": "discovery_search",
    "discovery.compare": "discovery_compare",
    "discovery.verdict": "discovery_verdict",
    "discovery.auctions": "discovery_auctions",
    "transaction.financing": "transaction_financing",
    "transaction.bid": "transaction_bid",
    "rag.knowledge": "rag_knowledge",
    "profile.summary": "profile_summary",
    "listings.sell": "listings_sell",
}

_CANCEL_WORDS = {"cancel", "stop", "never mind", "nevermind", "quit", "abort"}

_JOURNEY_BY_INTENT = {
    "discovery.search": "buying",
    "discovery.compare": "buying",
    "discovery.verdict": "buying",
    "discovery.auctions": "auctions",
    "transaction.financing": "financing",
    "transaction.bid": "bidding",
    "rag.knowledge": "knowledge",
    "profile.summary": "profile",
    "listings.sell": "selling",
}


def _deps(config) -> Deps:
    return config["configurable"]["deps"]


def _is_cancel(message: str) -> bool:
    m = message.strip().lower()
    return m in _CANCEL_WORDS or m.startswith("cancel")


def _router_node(state: GraphState, config, writer: StreamWriter) -> dict:
    deps = _deps(config)
    sid = state["session_id"]
    message = state["message"]
    context = deps.sessions.get_state(sid)

    if state.get("action_intent"):
        intent = state["action_intent"]
        entities = state.get("action_entities", {})
        if intent == "listings.sell":
            deps.sessions.update_state(sid, listing_draft_paused=False)
        deps.sessions.update_state(
            sid,
            active_journey=_JOURNEY_BY_INTENT[intent],
            last_intent=intent,
        )
        writer(Trace(
            kind="routing",
            label="ui_action",
            detail={"intent": intent, "action_type": state.get("ui_action", {}).get("type")},
        ))
        return {"intent": intent, "entities": entities}

    # Sticky listing draft: while an unfinished sell draft is active, bypass the LLM
    # classifier entirely and route to the Listings agent (cancel escapes the flow).
    draft = deps.sessions.get_listing_draft(sid)
    text = message.strip().lower()
    resume_listing = any(
        phrase in text for phrase in ("resume listing", "continue listing", "back to my listing")
    )
    pause_listing = any(
        phrase in text for phrase in (
            "pause listing", "pause this listing", "save and exit",
            "come back to this", "do something else",
        )
    )
    if draft is not None and resume_listing:
        deps.sessions.update_state(sid, listing_draft_paused=False)
        writer(Trace(
            kind="routing",
            label="session_continuation",
            detail={"intent": "listings.sell", "reason": "resumed_listing_draft"},
        ))
        return {"intent": "listings.sell", "entities": {"resume_only": True}}
    if draft is not None and pause_listing:
        deps.sessions.update_state(sid, listing_draft_paused=True)
        writer(Trace(
            kind="routing",
            label="session_continuation",
            detail={"intent": "profile.summary", "reason": "paused_listing_draft"},
        ))
        return {"intent": "profile.summary", "entities": {}}
    if draft is not None and not context.get("listing_draft_paused"):
        if _is_cancel(message):
            deps.sessions.clear_listing_draft(sid)
            deps.sessions.update_state(
                sid,
                active_journey="profile",
                last_intent="profile.summary",
                listing_draft_paused=False,
            )
            writer(Trace(kind="routing", label="intent",
                         detail={"intent": "profile.summary", "cancelled_draft": True}))
            return {"intent": "profile.summary", "entities": {}}
        deps.sessions.update_state(sid, active_journey="selling", last_intent="listings.sell")
        writer(Trace(kind="routing", label="intent",
                     detail={"intent": "listings.sell", "sticky_draft": True}))
        return {"intent": "listings.sell", "entities": {}}

    if context.get("awaiting_finance_price") and router._parse_price(message):
        entities = router._heuristic_entities(message, "transaction.financing")
        deps.sessions.update_state(
            sid, active_journey="financing", last_intent="transaction.financing"
        )
        writer(Trace(
            kind="routing",
            label="session_continuation",
            detail={"intent": "transaction.financing", "reason": "awaiting_finance_price"},
        ))
        return {"intent": "transaction.financing", "entities": entities}

    if context.get("awaiting_buy_criteria"):
        if _is_cancel(message):
            deps.sessions.update_state(
                sid,
                active_journey="profile",
                last_intent="profile.summary",
                awaiting_buy_criteria=False,
                buy_intake_step=None,
                search_constraints={},
            )
            writer(Trace(
                kind="routing",
                label="session_continuation",
                detail={"intent": "profile.summary", "reason": "cancelled_buy_intake"},
            ))
            return {"intent": "profile.summary", "entities": {}}
        _, entities, version = router.classify(
            message,
            deps,
            {
                "active_journey": "buying",
                "search_constraints": context.get("search_constraints", {}),
                "buy_intake_step": context.get("buy_intake_step"),
            },
        )
        deps.sessions.update_state(
            sid, active_journey="buying", last_intent="discovery.search"
        )
        writer(Trace(
            kind="routing",
            label="session_continuation",
            detail={
                "intent": "discovery.search",
                "reason": "awaiting_buy_criteria",
                "router_prompt": version,
            },
        ))
        return {"intent": "discovery.search", "entities": entities}

    # Preserve the subject of short knowledge follow-ups. The Knowledge agent
    # rewrites the turn against recent history before retrieval.
    if context.get("last_intent") == "rag.knowledge" and rag.is_contextual_followup(message):
        deps.sessions.update_state(sid, active_journey="knowledge", last_intent="rag.knowledge")
        writer(Trace(
            kind="routing",
            label="session_continuation",
            detail={"intent": "rag.knowledge", "reason": "knowledge_followup"},
        ))
        return {"intent": "rag.knowledge", "entities": {}}

    routing_context = {
        "active_journey": state.get("conversation_context", {}).get("active_journey"),
        "last_intent": state.get("conversation_context", {}).get("last_intent"),
        "focused_entity_type": state.get("conversation_context", {}).get("focused_entity_type"),
        "focused_entity_id": state.get("conversation_context", {}).get("focused_entity_id"),
        "conversation_summary": state.get("conversation_context", {}).get(
            "conversation_summary", ""
        )[-800:],
    }
    intent, entities, version = router.classify(message, deps, routing_context)
    if intent == "listings.sell":
        deps.sessions.update_state(sid, listing_draft_paused=False)
    deps.sessions.update_state(
        sid,
        active_journey=_JOURNEY_BY_INTENT[intent],
        last_intent=intent,
    )
    writer(Trace(kind="routing", label="intent",
                 detail={"intent": intent, "router_prompt": version}))
    return {"intent": intent, "entities": entities}


def _route(state: GraphState) -> str:
    return _INTENT_NODE.get(state.get("intent", ""), "discovery_search")


def _make_worker(fn):
    def node(state: GraphState, config, writer: StreamWriter) -> dict:
        deps = _deps(config)
        fn(state, deps, writer)
        return {}
    return node


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("router", _router_node)
    g.add_node("discovery_search", _make_worker(discovery.handle_search))
    g.add_node("discovery_compare", _make_worker(discovery.handle_compare))
    g.add_node("discovery_verdict", _make_worker(discovery.handle_verdict))
    g.add_node("discovery_auctions", _make_worker(discovery.handle_auctions))
    g.add_node("transaction_financing", _make_worker(transaction.handle_financing))
    g.add_node("transaction_bid", _make_worker(transaction.handle_bid))
    g.add_node("rag_knowledge", _make_worker(rag.handle_knowledge))
    g.add_node("profile_summary", _make_worker(profile.handle_profile))
    g.add_node("listings_sell", _make_worker(listings.handle_sell))

    g.set_entry_point("router")
    g.add_conditional_edges("router", _route, {v: v for v in _INTENT_NODE.values()})
    for node_name in _INTENT_NODE.values():
        g.add_edge(node_name, END)
    return g.compile()
