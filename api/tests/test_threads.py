from __future__ import annotations

from . import sse_helper as sse


def _sarah_auth(client) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": "sarah", "password": "demo1234"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_thread_lifecycle_and_owner_isolation(client, auth):
    created = client.post("/api/threads", headers=auth, json={})
    assert created.status_code == 201
    thread_id = created.json()["id"]

    listing = client.get("/api/threads", headers=auth)
    assert any(item["id"] == thread_id for item in listing.json()["items"])

    sarah = _sarah_auth(client)
    assert client.get(f"/api/threads/{thread_id}", headers=sarah).status_code == 404
    assert client.patch(
        f"/api/threads/{thread_id}", headers=sarah, json={"title": "stolen"}
    ).status_code == 404
    assert client.delete(f"/api/threads/{thread_id}", headers=sarah).status_code == 404
    assert client.post(
        "/api/chat",
        headers=sarah,
        json={"message": "Continue this", "thread_id": thread_id},
    ).status_code == 404

    renamed = client.patch(
        f"/api/threads/{thread_id}",
        headers=auth,
        json={"title": "My vehicle search"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "My vehicle search"

    assert client.delete(f"/api/threads/{thread_id}", headers=auth).status_code == 204
    assert client.get(f"/api/threads/{thread_id}", headers=auth).status_code == 404


def test_chat_persists_replayable_ordered_components(client, auth):
    thread = client.post("/api/threads", headers=auth, json={}).json()
    response = client.post(
        "/api/chat",
        headers=auth,
        json={
            "message": "Find me a Toyota Harrier under 6M",
            "thread_id": thread["id"],
        },
    )
    assert response.status_code == 200

    restored = client.get(f"/api/threads/{thread['id']}", headers=auth)
    assert restored.status_code == 200
    payload = restored.json()
    assert payload["title"] != "New conversation"
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]

    assistant = payload["messages"][1]
    blocks = assistant["content"]
    assert any(block["type"] == "text" for block in blocks)
    component_types = [
        block["component_type"] for block in blocks if block["type"] == "component"
    ]
    assert "car_card_list" in component_types
    assert "follow_up_suggestions" in component_types
    assert all(
        block.get("schema_version") == 1
        for block in blocks if block["type"] == "component"
    )
    assert assistant["trace"]
    assert assistant["tools"]


def test_thread_pagination(client, auth):
    ids = [
        client.post("/api/threads", headers=auth, json={"title": f"Thread {index}"}).json()["id"]
        for index in range(3)
    ]
    first = client.get("/api/threads?limit=2&cursor=0", headers=auth).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] == 2
    second = client.get(f"/api/threads?limit=2&cursor={first['next_cursor']}", headers=auth).json()
    returned = {item["id"] for item in [*first["items"], *second["items"]]}
    assert set(ids).issubset(returned)


def test_legacy_redis_turns_import_once_with_components(client, auth):
    session_id = "sess-legacy-import"
    scoped = client.app.state.sessions.scoped_id("usr_david", session_id)
    client.app.state.sessions.append_turn(
        scoped,
        turn_id="legacy-user",
        role="user",
        text="Show me auctions",
        components=[],
    )
    client.app.state.sessions.append_turn(
        scoped,
        turn_id="legacy-agent",
        role="assistant",
        text="Here are the auctions.",
        components=[{
            "type": "follow_up_suggestions",
            "props": {"suggestions": [{
                "id": "legacy",
                "label": "How do auctions work?",
                "action": {"type": "ask_knowledge", "topic": "How do auctions work?"},
            }]},
        }],
    )
    first = client.get(
        f"/api/session/bootstrap?session_id={session_id}", headers=auth
    )
    assert first.status_code == 200
    assert first.json()["thread_id"] == session_id
    restored = client.get(f"/api/threads/{session_id}", headers=auth).json()
    assert len(restored["messages"]) == 2
    assert restored["messages"][1]["content"][1]["component_type"] == "follow_up_suggestions"

    # Reopening bootstrap does not duplicate imported messages.
    client.get(f"/api/session/bootstrap?session_id={session_id}", headers=auth)
    assert len(client.get(f"/api/threads/{session_id}", headers=auth).json()["messages"]) == 2


def test_replayed_bid_modal_is_hydrated_after_confirmation(client, auth):
    thread_id = "sess-thread-bid-hydrate"
    sse.chat(client, auth, "Show me auctions", thread_id)
    events = sse.chat(client, auth, "Bid 1.9M on the Suzuki Vitara", thread_id)
    modal = next(c for c in sse.components(events) if c["type"] == "bid_confirm_modal")
    confirmed = client.post(
        "/api/bids/confirm",
        headers=auth,
        json={
            "signed_proposal": modal["props"]["signed_proposal"],
            "session_id": thread_id,
        },
    )
    assert confirmed.status_code == 200
    restored = client.get(f"/api/threads/{thread_id}", headers=auth).json()
    bid_blocks = [
        block
        for message in restored["messages"]
        for block in message["content"]
        if block.get("component_type") == "bid_confirm_modal"
    ]
    assert bid_blocks[-1]["props"]["action_status"] == "confirmed"
    assert bid_blocks[-1]["props"]["receipt"]["id"] == confirmed.json()["bid"]["id"]
