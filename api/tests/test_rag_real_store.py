from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc

from app.rag.store import RagStore


def test_real_embedding_store_retrieves_every_knowledge_domain():
    store = RagStore()
    store.initialize()
    cases = (
        ("How do online vehicle auctions work?", "auctions"),
        ("What documents qualify me for a car loan?", "financing"),
        ("Tell me about trading in my current car", "trade-in"),
        ("Can I exchange my existing vehicle for another one?", "trade-in"),
        ("Are marketplace cars inspected and returnable?", "policies"),
        ("How do payments and logbook transfers work?", "policies"),
        ("What motor cover is available?", "insurance"),
        ("Can I pay my insurance premium monthly?", "insurance"),
        ("Can my motor dealership get stock financing?", "dealer-finance"),
    )
    for query, category in cases:
        chunks = store.retrieve(query, k=3)
        assert chunks, query
        assert all(chunk.category == category for chunk in chunks), query
        assert chunks[0].score >= 0.15, query
        assert chunks[0].retrieved_at
        assert chunks[0].document_version
        assert -1 <= chunks[0].vector_score <= 1
        assert 0 <= chunks[0].lexical_score <= 1


def test_unknown_domain_is_not_forced_into_a_knowledge_category():
    assert RagStore.query_category(
        "Can CarDuka ship a rover to a colony on Mars?"
    ) is None


def test_real_store_remains_stable_across_repeated_concurrent_categories():
    store = RagStore()
    store.initialize()
    gc.collect()
    queries = (
        "How does trade-in work?",
        "What motor cover is available?",
        "Can my dealership get stock financing?",
        "How do payments and logbook transfers work?",
        "How do online vehicle auctions work?",
        "What documents qualify me for a car loan?",
    ) * 3
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda query: store.retrieve(query, k=3), queries))
    assert all(results)
    assert all(len({chunk.category for chunk in chunks}) == 1 for chunks in results)


def test_hybrid_retrieval_ranks_expected_source_for_paraphrases():
    store = RagStore()
    store.initialize()
    cases = (
        ("Can I spread the cost of my motor policy monthly?",
         {"kb_insurance_premium_finance", "kb_insurance"}),
        ("What happens to my old ride when I want a replacement?",
         {"kb_tradein_marketplace", "kb_tradein_process"}),
        ("What paperwork proves I can afford vehicle credit?",
         {"kb_financing_eligibility", "kb_financing_process"}),
        ("Who keeps the money before handover?",
         {"kb_payments"}),
    )
    hits = 0
    reciprocal_ranks = []
    for query, expected_ids in cases:
        chunks = store.retrieve(query, k=3)
        ranks = [
            index for index, chunk in enumerate(chunks, start=1)
            if chunk.source_id in expected_ids
        ]
        if ranks:
            hits += 1
            reciprocal_ranks.append(1 / ranks[0])
    assert hits / len(cases) >= 0.75  # Recall@3
    assert sum(reciprocal_ranks) / len(cases) >= 0.60  # MRR
