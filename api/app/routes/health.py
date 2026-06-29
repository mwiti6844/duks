"""GET /api/health — readiness gate. Returns 503 until seed + embeddings complete."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request, response: Response) -> dict:
    readiness = request.app.state.readiness
    payload = readiness.status()
    if payload["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
