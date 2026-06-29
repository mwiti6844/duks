"""Transport-neutral execution events.

Graph nodes publish these as work happens (via LangGraph's stream writer); the SSE
adapter serializes them. Agents never touch SSE directly — this keeps genuine
token/tool streaming while the graph stays transport-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolStarted:
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCompleted:
    name: str
    ms: int
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentReady:
    type: str
    props: dict[str, Any]


@dataclass
class Trace:
    kind: str
    label: str
    detail: dict[str, Any] = field(default_factory=dict)


AgentExecutionEvent = TextDelta | ToolStarted | ToolCompleted | ComponentReady | Trace
