from __future__ import annotations

from . import sse_helper as sse


def test_knowledge_answer_has_citations(client, auth):
    events = sse.chat(client, auth, "How do auctions work?", "sess-rag")
    ka = next(c for c in sse.components(events) if c["type"] == "knowledge_answer")
    citations = ka["props"]["citations"]
    assert citations
    # Citations come from retrieved chunk metadata.
    assert all("source_id" in c and "title" in c for c in citations)
    assert any(c["source_id"].startswith("kb_") for c in citations)


def test_unsupported_policy_declines(client, auth):
    events = sse.chat(
        client, auth,
        "What is CarDuka's policy on interplanetary vehicle shipping to Mars?",
        "sess-rag-decline",
    )
    # No knowledge component when nothing relevant is retrieved; agent declines.
    assert not any(c["type"] == "knowledge_answer" for c in sse.components(events))
    assert "support" in sse.text(events).lower() or "don't have" in sse.text(events).lower()


def test_service_journeys_use_linked_official_sources(client, auth):
    for i, question in enumerate((
        "How does CarDuka trade-in work?",
        "How does CarDuka vehicle insurance work?",
        "How does CarDuka dealership financing work?",
    )):
        events = sse.chat(client, auth, question, f"sess-rag-service-{i}")
        answer = next(c for c in sse.components(events) if c["type"] == "knowledge_answer")
        citations = answer["props"]["citations"]
        assert citations
        assert any(
            c.get("source_url", "").startswith("https://www.carduka.com/")
            for c in citations
        )
