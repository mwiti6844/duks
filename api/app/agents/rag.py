"""RAG Knowledge Agent: answers policy/process questions grounded in retrieved chunks.

Citations come from chunk metadata. If retrieval returns nothing relevant, the agent
declines rather than fabricating policy. RAG docs are treated as untrusted reference.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from ..prompts import load_prompt
from . import suggestions
from .context import prompt_context
from .deps import Deps
from .events import ComponentReady, TextDelta, ToolCompleted, ToolStarted, Trace
from .state import GraphState

Emit = Callable[[object], None]

_MIN_RELEVANCE = 0.30
_DOMAIN_MIN_RELEVANCE = 0.15
_VAGUE_FOLLOWUPS = {
    "what about that", "what about it", "tell me more", "how does that work",
    "what do i need", "what documents do i need", "and the requirements",
}


def is_contextual_followup(message: str) -> bool:
    """Whether a short turn reasonably depends on the preceding knowledge turn."""
    normalized = " ".join(message.lower().split()).rstrip("?.!")
    # An explicitly named service is already standalone, even when phrased briefly.
    if any(term in normalized for term in (
        "auction", "financ", "loan", "trade-in", "trade in", "insurance",
        "insure", "dealer", "dealership", "payment", "logbook", "inspection",
    )):
        return False
    if normalized in _VAGUE_FOLLOWUPS:
        return True
    if len(normalized.split()) > 9:
        return False
    return bool(
        set(normalized.split())
        & {
            "it", "that", "those", "they", "documents", "requirements",
            "eligible", "cost", "fees", "steps", "apply", "needed", "need",
        }
    )


def _standalone_query(state: GraphState, query: str) -> tuple[str, bool]:
    """Resolve a knowledge follow-up using recent user turns.

    Returns (query, needs_clarification). The rewrite is deterministic and visible
    in the trace; it never invents facts or silently changes a specific question.
    """
    normalized = " ".join(query.lower().split()).rstrip("?.!")
    history = state.get("recent_history", [])
    previous_users = [
        item.get("content", "").strip()
        for item in history[:-1]
        if item.get("role") == "user" and item.get("content", "").strip()
    ]
    is_vague = is_contextual_followup(query)
    if not is_vague:
        return query, False
    if not previous_users:
        return query, True
    return f"{previous_users[-1]}\nFollow-up question: {query}", False


def _evidence_set(chunks: list, threshold: float, *, limit: int = 2) -> list:
    """Select a compact, source-deduplicated set that generation must use."""
    selected = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.score < threshold or chunk.source_id in seen:
            continue
        selected.append(chunk)
        seen.add(chunk.source_id)
        if len(selected) >= limit:
            break
    return selected


def handle_knowledge(state: GraphState, deps: Deps, emit: Emit) -> None:
    raw_query = state.get("entities", {}).get("topic") or state["message"]
    query, needs_clarification = _standalone_query(state, raw_query)
    if needs_clarification:
        emit(TextDelta(
            text="Which CarDuka service do you mean—financing, trade-in, "
                 "insurance, dealership finance, auctions, or marketplace policies?"
        ))
        emit(Trace(kind="retrieval", label="clarification_required",
                   detail={"query": raw_query}))
        return

    emit(ToolStarted(name="rag_retrieve", params={"query": query}))
    t0 = time.time()
    try:
        chunks = deps.rag.retrieve(query, k=6)
    except Exception as exc:
        emit(ToolCompleted(
            name="rag_retrieve",
            ms=int((time.time() - t0) * 1000),
            detail={"status": "failed", "error_type": type(exc).__name__},
        ))
        emit(Trace(kind="retrieval", label="retrieval_failed",
                   detail={"error_type": type(exc).__name__}))
        raise
    emit(ToolCompleted(name="rag_retrieve", ms=int((time.time() - t0) * 1000),
                       detail={
                           "retrieved": [c.source_id for c in chunks],
                           "effective_query": query,
                       }))
    if query != raw_query:
        emit(Trace(kind="retrieval", label="query_rewrite",
                   detail={"original": raw_query, "effective": query}))

    category_fn = getattr(deps.rag, "query_category", None)
    category = category_fn(query) if callable(category_fn) else None
    threshold = _DOMAIN_MIN_RELEVANCE if category else _MIN_RELEVANCE
    relevant = _evidence_set(chunks, threshold)
    citations = [{"source_id": c.source_id, "title": c.title, "score": c.score,
                  "source_url": c.source_url, "section": c.section,
                  "document_version": c.document_version,
                  "retrieved_at": c.retrieved_at}
                 for c in relevant]
    for c in relevant:
        emit(Trace(kind="retrieval", label=c.title,
                   detail={
                       "source_id": c.source_id,
                       "score": c.score,
                       "vector_score": c.vector_score,
                       "lexical_score": c.lexical_score,
                   }))

    if not relevant:
        emit(TextDelta(text="I don't have that in CarDuka's documented policies. Please "
                            "contact CarDuka support and they'll help directly."))
        return

    context = "\n\n".join(f"[{c.source_id}] {c.title}: {c.text}" for c in relevant)
    system, version = load_prompt("rag.v1")
    emit(Trace(kind="prompt", label="prompt_version", detail={"version": version}))
    system = system.replace("{context}", context)

    # Stream the answer; the model may still decline if the passages don't actually
    # answer the question (groundedness is the generator's call).
    answer_parts: list[str] = []
    for chunk in deps.llm.stream_text(
        system=system, user=prompt_context(state, query), max_tokens=400
    ):
        answer_parts.append(chunk)
        emit(TextDelta(text=chunk))
    answer = "".join(answer_parts).strip()

    # Only attach citation chips to a genuinely grounded answer — never to a decline.
    if _is_decline(answer):
        return
    emit(ComponentReady(type="knowledge_answer", props={
        "answer": answer,
        "citations": citations,
    }))
    followups = suggestions.after_knowledge(query)
    if followups:
        emit(followups)


def _is_decline(answer: str) -> bool:
    low = answer.lower()
    return ("don't have" in low or "contact carduka support" in low
            or "do not have" in low)
