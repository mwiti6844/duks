"""JWT mint/verify. Only the api service holds JWT_SECRET; the web BFF treats the
token as opaque."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(hours=12)


def create_token(secret: str, *, user_id: str, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + _TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_token(secret: str, token: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except JWTError:
        return None
