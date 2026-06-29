from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings


def test_fail_fast_without_any_provider_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("USE_FAKE_LLM", raising=False)
    with pytest.raises(ConfigError):
        load_settings(allow_fake=False)


def test_allow_fake_bypasses_key_requirement(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = load_settings(allow_fake=True)
    assert settings.use_fake_llm is True


def test_anthropic_key_disables_fake(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = load_settings(allow_fake=False)
    assert settings.use_fake_llm is False
    assert settings.anthropic_model == "claude-sonnet-4-6"
