"""Parse the SSE stream returned by POST /api/chat into a list of (event, data)."""
from __future__ import annotations

import json


def chat(client, auth: dict, message: str, session_id: str = "test-sess") -> list[tuple[str, dict]]:
    resp = client.post(
        "/api/chat",
        headers=auth,
        json={"message": message, "session_id": session_id},
    )
    assert resp.status_code == 200, resp.text
    events: list[tuple[str, dict]] = []
    event_name = None
    for line in resp.text.splitlines():
        if line.startswith("event: "):
            event_name = line[len("event: "):]
        elif line.startswith("data: ") and event_name:
            events.append((event_name, json.loads(line[len("data: "):])))
    return events


def components(events: list[tuple[str, dict]]) -> list[dict]:
    return [d for e, d in events if e == "component"]


def text(events: list[tuple[str, dict]]) -> str:
    return "".join(d["text"] for e, d in events if e == "token")
