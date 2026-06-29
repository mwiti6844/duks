"""Versioned prompt loading. The version id is logged into the sanitized trace."""
from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str) -> tuple[str, str]:
    """Return (text, version_id) for prompts/<name>.txt. version_id is the filename stem."""
    path = _DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8"), name
