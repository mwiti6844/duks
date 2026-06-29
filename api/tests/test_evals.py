"""Eval fixtures: routing accuracy, tool selection, grounded answers, scripted flows.

These complement the unit tests with corpus-style checks over the fake provider's
deterministic routing + the real RAG/DB pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.agents import router
from app.agents.deps import Deps
from app.llm.provider import FakeProvider

from . import sse_helper as sse

_EVALS = Path(__file__).parent / "evals"


class _StubSessions:
    def get_state(self, sid):
        return {}


def _router_deps():
    return Deps(db_factory=None, rag=None, llm=FakeProvider(), sessions=_StubSessions(),
                settings=None)


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (_EVALS / name).read_text().splitlines() if line.strip()]


def test_routing_accuracy():
    deps = _router_deps()
    rows = _load("routing.jsonl")
    correct = sum(1 for r in rows if router.classify(r["message"], deps)[0] == r["intent"])
    accuracy = correct / len(rows)
    assert accuracy >= 0.9, f"routing accuracy {accuracy:.2%}"


def test_tool_selection(client, auth):
    for i, row in enumerate(_load("tool_selection.jsonl")):
        events = sse.chat(client, auth, row["message"], f"sess-toolsel-{i}")
        tools_used = {d["name"] for e, d in events if e == "tool"}
        if row.get("expect_no_tool"):
            assert not tools_used, f"{row['message']} -> {tools_used}"
            if expected_text := row.get("expect_text"):
                assert expected_text.lower() in sse.text(events).lower()
        else:
            assert row["expect_tool"] in tools_used, f"{row['message']} -> {tools_used}"


def test_grounded_answers(client, auth):
    for i, row in enumerate(_load("grounded_answers.jsonl")):
        events = sse.chat(client, auth, row["message"], f"sess-ground-{i}")
        comps = sse.components(events)
        ka = [c for c in comps if c["type"] == "knowledge_answer"]
        if row["should_answer"]:
            assert ka, row["message"]
            assert all(c["source_id"].startswith(row["expect_source_prefix"])
                       for c in ka[0]["props"]["citations"])
        else:
            assert not ka, f"should have declined: {row['message']}"


def test_scripted_flows(client, auth):
    for row in _load("flows.jsonl"):
        sid = f"sess-flow-{row['name']}"
        seen: set[str] = set()
        for turn in row["turns"]:
            events = sse.chat(client, auth, turn, sid)
            seen.update(c["type"] for c in sse.components(events))
        for expected in row["expect_components"]:
            assert expected in seen, f"{row['name']} missing {expected}"
