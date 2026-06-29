"""POST /api/chat — SSE stream. Runs the LangGraph agent and serializes its custom
execution-event stream into SSE frames via the adapter."""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agents.events import ComponentReady, TextDelta, Trace
from ..agents.actions import ActionError, AskKnowledgeAction, UIAction, resolve_action
from ..agents.result import AgentResult, Citation, TraceEntry, validated_component
from ..agents.router import _parse_price
from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import UserDTO
from ..db.engine import SessionLocal
from ..streaming.sse_adapter import events_to_sse

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    session_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    action: UIAction | None = None


def _capture_confirmed_user_memory(user_id: str, message: str) -> dict:
    """Persist only preferences the user explicitly states as their own."""
    text = message.lower()
    preference_language = any(
        phrase in text for phrase in ("i prefer", "i like", "i'm looking for",
                                      "i am looking for", "my preferred")
    )
    budget_language = any(
        phrase in text for phrase in ("my budget", "i can spend", "budget is", "budget of")
    )
    with SessionLocal() as db:
        makes, body_types = repo.distinct_vehicle_facets(db)
        preferred_make = next(
            (make for make in makes if preference_language and make.lower() in text), None
        )
        if preference_language and preferred_make is None:
            open_make = re.search(
                r"\b(?:i prefer|i like|my preferred make is)\s+(?:an?\s+)?"
                r"([a-z][a-z-]*)\b",
                text,
            )
            if open_make:
                preferred_make = open_make.group(1).title()
        preferred_body_type = next(
            (kind for kind in body_types if preference_language and kind.lower() in text), None
        )
        budget = _parse_price(message) if budget_language else None
        if budget or preferred_make or preferred_body_type:
            return repo.update_user_memory(
                db,
                user_id=user_id,
                budget_kes=budget,
                preferred_make=preferred_make,
                preferred_body_type=preferred_body_type,
            ).model_dump()
        return repo.get_user_memory(db, user_id).model_dump()


@router.post("/chat")
def chat(
    body: ChatRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
) -> StreamingResponse:
    app = request.app
    graph = app.state.graph
    deps = app.state.deps
    sessions = app.state.sessions

    sid = sessions.scoped_id(user.id, body.session_id)
    resolved_action = None
    if body.action is not None:
        try:
            resolved_action = resolve_action(body.action, sid=sid, deps=deps)
        except ActionError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    sessions.ensure_turns_from_history(sid)
    sessions.append_history(sid, "user", body.message)
    sessions.append_turn(
        sid,
        turn_id=f"turn_{uuid.uuid4().hex}",
        role="user",
        text=body.message,
        components=[],
    )
    recent_history = sessions.get_history(sid)[-12:]
    conversation_context = sessions.get_state(sid)
    user_memory = _capture_confirmed_user_memory(user.id, body.message)

    initial_state = {
        "user_id": user.id,
        "username": user.username,
        "session_id": sid,
        "message": (
            body.action.topic
            if isinstance(body.action, AskKnowledgeAction)
            else body.message
        ),
        "recent_history": recent_history,
        "conversation_context": conversation_context,
        "user_memory": user_memory,
        "ui_action": body.action.model_dump() if body.action else {},
        "action_intent": resolved_action.intent if resolved_action else "",
        "action_entities": resolved_action.entities if resolved_action else {},
    }
    config = {"configurable": {"deps": deps}}

    def event_stream() -> Iterator[object]:
        assistant_text: list[str] = []
        components = []
        citations: dict[str, Citation] = {}
        trace: list[TraceEntry] = []
        for event in graph.stream(initial_state, config, stream_mode="custom"):
            if isinstance(event, TextDelta):
                assistant_text.append(event.text)
            elif isinstance(event, ComponentReady):
                component = validated_component(event.type, event.props)
                if component:
                    components.append(component)
                    if event.type == "knowledge_answer":
                        for item in component.props.get("citations", []):
                            citation = Citation.model_validate(item)
                            citations[citation.source_id] = citation
            elif isinstance(event, Trace):
                trace.append(TraceEntry(kind=event.kind, label=event.label, detail=event.detail))
            yield event
        # Persist the assistant turn once streaming finishes.
        full = "".join(assistant_text).strip()
        if full:
            sessions.append_history(sid, "assistant", full)
        sessions.refresh_summary(sid)
        result = AgentResult(
            text=full,
            components=components,
            citations=list(citations.values()),
            trace=trace,
        )
        sessions.set_last_result(sid, result.model_dump(mode="json"))
        if full or components:
            sessions.append_turn(
                sid,
                turn_id=f"turn_{uuid.uuid4().hex}",
                role="assistant",
                text=full,
                components=[item.model_dump(mode="json") for item in components],
            )

    return StreamingResponse(
        events_to_sse(event_stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
