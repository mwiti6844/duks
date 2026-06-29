"""Runtime configuration. Validated at startup; fails fast on missing provider keys."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    groq_api_key: str | None
    anthropic_model: str
    groq_model: str
    jwt_secret: str
    bid_signing_secret: str
    redis_url: str | None
    allow_in_memory_sessions: bool
    # When True, the LLM layer uses a deterministic fake (tests / keyless demo).
    use_fake_llm: bool

    @property
    def has_any_provider(self) -> bool:
        return bool(self.anthropic_api_key or self.groq_api_key)


def load_settings(*, allow_fake: bool = False) -> Settings:
    """Build Settings from the environment.

    `allow_fake` is set by the application factory in tests so the app can boot
    without real keys. In production (`allow_fake=False`) at least one provider
    key is required, or we raise ConfigError before serving traffic.
    """
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
    groq_api_key = os.getenv("GROQ_API_KEY") or None

    use_fake_llm = False
    if not anthropic_api_key and not groq_api_key:
        if allow_fake or os.getenv("USE_FAKE_LLM") == "1":
            use_fake_llm = True
        else:
            raise ConfigError(
                "No LLM provider key configured. Set ANTHROPIC_API_KEY (and "
                "optionally GROQ_API_KEY) before starting the API."
            )

    return Settings(
        anthropic_api_key=anthropic_api_key,
        groq_api_key=groq_api_key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        jwt_secret=os.getenv("JWT_SECRET", "dev-jwt-secret"),
        bid_signing_secret=os.getenv("BID_SIGNING_SECRET", "dev-bid-secret"),
        redis_url=os.getenv("REDIS_URL") or None,
        allow_in_memory_sessions=(
            os.getenv("ALLOW_IN_MEMORY_SESSIONS", "").lower() in ("1", "true", "yes")
            or not (
                os.getenv("APP_ENV", "").lower() == "production"
                or bool(os.getenv("RAILWAY_ENVIRONMENT"))
            )
        ),
        use_fake_llm=use_fake_llm,
    )
