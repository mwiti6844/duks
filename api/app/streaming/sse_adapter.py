"""Serialize AgentExecutionEvents into SSE frames.

Components are validated against their allow-listed Pydantic schema before they are
streamed; invalid payloads are dropped and an error frame is emitted instead.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

from ..agents.events import (
    ComponentReady,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    Trace,
)
from ..agents.result import ComponentType, validated_component


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def events_to_sse(events: Iterable[object]) -> Iterator[str]:
    """Turn the graph's custom event stream into SSE text frames.

    The upstream graph iterator is wrapped so any node-level exception is surfaced as
    an `error` frame and the stream still terminates with a `done` frame — the client
    never sees a truncated stream.
    """
    try:
        yield from _serialize(events)
    except Exception as exc:  # pragma: no cover - defensive stream guard
        yield _frame("error", {"message": f"The agent hit an error: {exc}"})
    yield _frame("done", {})


def _serialize(events: Iterable[object]) -> Iterator[str]:
    for ev in events:
        if isinstance(ev, TextDelta):
            if ev.text:
                yield _frame("token", {"text": ev.text})
        elif isinstance(ev, ToolStarted):
            yield _frame("tool", {"name": ev.name, "status": "started", "params": ev.params})
        elif isinstance(ev, ToolCompleted):
            yield _frame("tool", {"name": ev.name, "status": "completed",
                                  "ms": ev.ms, "detail": ev.detail})
        elif isinstance(ev, Trace):
            yield _frame("trace", {"kind": ev.kind, "label": ev.label, "detail": ev.detail})
        elif isinstance(ev, ComponentReady):
            try:
                ComponentType(ev.type)
            except ValueError:
                yield _frame("error", {"message": f"Unknown component type: {ev.type}"})
                continue
            component = validated_component(ev.type, ev.props)
            if component is None:
                yield _frame("error", {"message": f"Invalid props for component {ev.type}"})
                continue
            yield _frame("component",
                         {"type": component.type.value, "props": component.props})
        # Unknown event objects are ignored defensively.
