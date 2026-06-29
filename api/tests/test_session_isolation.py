from __future__ import annotations

from . import sse_helper as sse


def test_sessions_are_scoped_to_authenticated_user(client, auth):
    session_id = "sess-shared-browser-id"
    sse.chat(client, auth, "Find me a Toyota Fielder", session_id)

    login = client.post(
        "/api/auth/login",
        json={"username": "sarah", "password": "demo1234"},
    )
    assert login.status_code == 200
    sarah_auth = {"Authorization": f"Bearer {login.json()['token']}"}

    bootstrap = client.get(
        "/api/session/bootstrap",
        headers=sarah_auth,
        params={"session_id": session_id},
    )
    assert bootstrap.status_code == 200
    assert bootstrap.json()["history"] == []
    assert bootstrap.json()["pending_bid"] is None
