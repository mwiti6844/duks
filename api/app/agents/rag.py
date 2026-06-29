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


def handle_knowledge(state: GraphState, deps: Deps, emit: Emit) -> None:
    query = state.get("entities", {}).get("topic") or state["message"]
    emit(ToolStarted(name="rag_retrieve", params={"query": query}))
    t0 = time.time()
    chunks = deps.rag.retrieve(query, k=3)
    emit(ToolCompleted(name="rag_retrieve", ms=int((time.time() - t0) * 1000),
                       detail={"retrieved": [c.source_id for c in chunks]}))

    relevant = [c for c in chunks if c.score >= _MIN_RELEVANCE]
    citations = [{"source_id": c.source_id, "title": c.title, "score": c.score,
                  "source_url": c.source_url}
                 for c in relevant]
    for c in relevant:
        emit(Trace(kind="retrieval", label=c.title,
                   detail={"source_id": c.source_id, "score": c.score}))

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
