"""LLMProvider abstraction.

Claude (claude-sonnet-4-6) is the default for the router and worker agents.
Groq (llama-3.3-70b-versatile) is a failover only: if Anthropic errors out, the
streaming text path falls back to Groq. A deterministic fake is injectable for
tests / keyless demos.

Two surfaces:
  - complete_json(): single-shot, used by the router for intent classification.
  - stream_text():   token stream, used by worker agents for the assistant prose.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Protocol

from ..config import Settings


class LLMProvider(Protocol):
    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict: ...

    def stream_text(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[str]: ...

    @property
    def label(self) -> str: ...


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


class ClaudeProvider:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    @property
    def label(self) -> str:
        return f"claude:{self._model}"

    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return _extract_json(text)

    def stream_text(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[str]:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for text in stream.text_stream:
                yield text


class GroqProvider:
    def __init__(self, api_key: str, model: str) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    @property
    def label(self) -> str:
        return f"groq:{self._model}"

    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return _extract_json(resp.choices[0].message.content or "")

    def stream_text(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class FakeProvider:
    """Deterministic provider for tests / keyless demo. Heuristic intent + canned prose."""

    @property
    def label(self) -> str:
        return "fake"

    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        if "LISTING_EXTRACTION" in system:
            return {"fields": self._fake_listing_fields(user)}
        # Return an empty intent so the router falls back to its deterministic
        # heuristic — that path is what the demo relies on when keyless.
        return {"intent": "", "entities": {}}

    @staticmethod
    def _fake_listing_fields(user: str) -> dict:
        """Test/keyless-mode extraction double. Production uses a real provider."""
        try:
            request = json.loads(user)
        except json.JSONDecodeError:
            return {}
        message = str(request.get("latest_user_message", "")).strip()
        current = request.get("current_missing_field")
        t = message.lower()
        fields: dict = {}

        makes = ("Toyota", "Subaru", "Nissan", "Lexus", "Suzuki", "Mazda", "Audi")
        models = ("Fielder", "Forester", "Premio", "Note", "LX", "Vitara", "Demio")
        for make in makes:
            if make.lower() in t:
                fields["make"] = make
                break
        for model in models:
            if re.search(rf"\b{re.escape(model.lower())}\b", t):
                fields["model"] = model
                break

        year = re.search(r"\b(19\d{2}|20\d{2})\b", t)
        if year:
            fields["year"] = int(year.group(1))
        mileage = re.search(r"(\d[\d,]*)\s*(?:km|kms|kilomet)", t)
        if mileage:
            fields["mileage_km"] = int(mileage.group(1).replace(",", ""))
        millions = re.search(r"(\d+(?:\.\d+)?)\s*m\b", t)
        if millions:
            fields["price_kes"] = int(float(millions.group(1)) * 1_000_000)

        vocab = {
            "transmission": ("Automatic", "Manual"),
            "fuel": ("Petrol", "Diesel", "Hybrid", "Electric"),
            "condition": ("Excellent", "Good", "Fair", "Needs repair"),
            "body_type": ("SUV", "Sedan", "Hatchback", "Station Wagon", "Pickup"),
        }
        for key, values in vocab.items():
            for value in values:
                if value.lower() in t:
                    fields[key] = value
                    break

        if current in ("make", "model", "transmission", "fuel", "condition",
                       "body_type", "location", "description") and not fields.get(current):
            # A short answer to the current question is unambiguous in the test double.
            if current == "description" and message:
                fields[current] = message
            elif message and len(message.split()) <= 4 and "sell" not in t:
                fields[current] = message
        if current in ("mileage_km", "price_kes") and current not in fields:
            number = re.fullmatch(r"\s*(\d[\d,]*)\s*", message)
            if number:
                fields[current] = int(number.group(1).replace(",", ""))
        return fields

    # Generic terms that appear across the KB and shouldn't count as grounding.
    _GENERIC = {"carduka", "policy", "policies", "vehicle", "vehicles", "price",
                "prices", "what", "does", "work", "works", "your", "about"}
    _DECLINE = ("I don't have that in CarDuka's documented policies. Please contact "
                "CarDuka support and they'll help directly.")

    def stream_text(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[str]:
        # Knowledge-agent grounding check: the rag prompt embeds the retrieved
        # context. If the query's distinctive terms are absent from that context,
        # decline (mirrors how the real model refuses unsupported claims).
        if "Retrieved context:" in system:
            context = system.split("Retrieved context:", 1)[1].lower()
            terms = {w for w in re.findall(r"[a-z]+", user.lower())
                     if len(w) > 4 and w not in self._GENERIC}
            grounded = any(w in context for w in terms) if terms else False
            if not grounded:
                for word in self._DECLINE.split():
                    yield word + " "
                return
            for word in ("Based", "on", "CarDuka's", "documentation:", "here", "is",
                         "what", "applies", "to", "your", "question."):
                yield word + " "
            return
        for word in ("Here", "is", "what", "I", "found", "for", "you."):
            yield word + " "


class FailoverProvider:
    """Wraps Claude with a Groq fallback for the streaming text path."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def label(self) -> str:
        return self._primary.label

    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        try:
            return self._primary.complete_json(system=system, user=user, max_tokens=max_tokens)
        except Exception:
            if self._fallback:
                return self._fallback.complete_json(system=system, user=user, max_tokens=max_tokens)
            raise

    def stream_text(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[str]:
        try:
            yield from self._primary.stream_text(system=system, user=user, max_tokens=max_tokens)
        except Exception:
            if not self._fallback:
                raise
            yield from self._fallback.stream_text(system=system, user=user, max_tokens=max_tokens)


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the runtime provider from settings (Claude default, Groq failover)."""
    if settings.use_fake_llm:
        return FakeProvider()

    primary: LLMProvider | None = None
    fallback: LLMProvider | None = None
    if settings.anthropic_api_key:
        primary = ClaudeProvider(settings.anthropic_api_key, settings.anthropic_model)
    if settings.groq_api_key:
        groq = GroqProvider(settings.groq_api_key, settings.groq_model)
        if primary is None:
            primary = groq  # Groq-only deployment
        else:
            fallback = groq

    if primary is None:  # pragma: no cover - config.load_settings guards this
        raise RuntimeError("No LLM provider available")
    return FailoverProvider(primary, fallback)
