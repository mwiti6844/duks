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

    if state.get("action_intent"):
        intent = state["action_intent"]
        entities = state.get("action_entities", {})
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
    if draft is not None:
        if _is_cancel(message):
            deps.sessions.clear_listing_draft(sid)
            deps.sessions.update_state(sid, active_journey="profile", last_intent="profile.summary")
            writer(Trace(kind="routing", label="intent",
                         detail={"intent": "profile.summary", "cancelled_draft": True}))
            return {"intent": "profile.summary", "entities": {}}
        deps.sessions.update_state(sid, active_journey="selling", last_intent="listings.sell")
        writer(Trace(kind="routing", label="intent",
                     detail={"intent": "listings.sell", "sticky_draft": True}))
        return {"intent": "listings.sell", "entities": {}}

    context = deps.sessions.get_state(sid)
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
