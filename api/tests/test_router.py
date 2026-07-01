from __future__ import annotations

from app.agents import router
from app.llm.provider import FakeProvider
from app.agents.deps import Deps


class _StubSessions:
    def get_state(self, sid):
        return {}


def _deps():
    return Deps(db_factory=None, rag=None, llm=FakeProvider(), sessions=_StubSessions(),
                settings=None)


class _WrongButValidProvider(FakeProvider):
    """Models can confidently return the wrong member of the valid intent enum."""

    def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        return {"intent": "rag.knowledge", "entities": {}}


def _wrong_intent_deps():
    return Deps(db_factory=None, rag=None, llm=_WrongButValidProvider(),
                sessions=_StubSessions(), settings=None)


def test_classify_search():
    intent, ent, _ = router.classify("Find me a Subaru Forester under 2.5M", _deps())
    assert intent == "discovery.search"
    assert ent["make"] == "Subaru"
    assert ent["model"] == "Forester"
    assert ent["max_price_kes"] == 2_500_000


def test_classify_compare():
    intent, _, _ = router.classify("Compare the first two", _deps())
    assert intent == "discovery.compare"


def test_classify_bid_amount():
    intent, ent, _ = router.classify("Bid 1.8M on the Forester", _deps())
    assert intent == "transaction.bid"
    assert ent["amount_kes"] == 1_800_000


def test_classify_knowledge():
    intent, _, _ = router.classify("How do auctions work?", _deps())
    assert intent == "rag.knowledge"


def test_classify_actionable_sell():
    intent, _, _ = router.classify("Sell my Fielder", _deps())
    assert intent == "listings.sell"
    intent, _, _ = router.classify("I want to sell my car", _deps())
    assert intent == "listings.sell"


def test_explicit_sell_overrides_wrong_but_valid_llm_intent():
    for message in ("I want to sell my car", "Sell my 2016 Toyota Fielder"):
        intent, _, _ = router.classify(message, _wrong_intent_deps())
        assert intent == "listings.sell"


def test_classify_sell_question_is_knowledge_not_listing():
    # "How do I sell …" is informational → RAG, NOT the listings draft flow.
    intent, _, _ = router.classify("How do I sell a car on CarDuka?", _deps())
    assert intent == "rag.knowledge"


def test_classify_informational_buttons():
    for q in ("How does CarDuka vehicle insurance work?",
              "How does CarDuka dealership financing work?",
              "How does CarDuka trade-in work?"):
        intent, _, _ = router.classify(q, _deps())
        assert intent == "rag.knowledge", q


def test_classify_knowledge_paraphrases_by_domain_concept():
    for question in (
        "What motor cover is available?",
        "Can I exchange my existing vehicle for another one?",
        "Which documents does a dealership need for stock financing?",
        "Are marketplace cars inspected and returnable?",
    ):
        intent, _, _ = router.classify(question, _deps())
        assert intent == "rag.knowledge", question


def test_focused_car_spec_question_overrides_wrong_rag_intent():
    # A vehicle-fact question about the focused car must reach the DB detail path,
    # even when the LLM confidently (and validly) returns rag.knowledge.
    context = {"focused_entity_type": "used_car", "focused_entity_id": "car_real_01"}
    for message in ("How many CC does this car have?",
                    "What colour is it?",
                    "What trim is this one?"):
        intent, _, _ = router.classify(message, _wrong_intent_deps(), context)
        assert intent == "discovery.search", message


def test_focused_policy_question_still_routes_to_rag():
    # With a car focused, a genuine policy question must NOT be stolen by the
    # vehicle-fact override.
    context = {"focused_entity_type": "used_car", "focused_entity_id": "car_real_01"}
    intent, _, _ = router.classify("How does trade-in work?", _deps(), context)
    assert intent == "rag.knowledge"


def test_spec_question_without_focused_car_is_unchanged():
    # No focused car → the override does not fire (avoids hijacking fresh searches).
    intent, _, _ = router.classify("Show me cars with a big engine", _deps())
    assert intent == "discovery.search"


def test_classify_financing():
    intent, _, _ = router.classify("What would financing look like?", _deps())
    assert intent == "transaction.financing"


def test_price_parsing_variants():
    _, ent, _ = router.classify("show cars under KES 2,500,000", _deps())
    assert ent["max_price_kes"] == 2_500_000
