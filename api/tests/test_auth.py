from __future__ import annotations


def test_health_ready(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "david", "password": "demo1234"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["full_name"] == "David Mwangi"
    assert "role" not in body["user"]
    assert body["token"]


def test_login_bad_password(client):
    resp = client.post("/api/auth/login", json={"username": "david", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client, auth):
    resp = client.get("/api/auth/me", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["username"] == "david"
