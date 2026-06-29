"""ASGI entrypoint for uvicorn. Production app: fail-fast on missing provider keys."""
from __future__ import annotations

from .factory import create_app

app = create_app()
