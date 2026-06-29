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


def test_classify_financing():
    intent, _, _ = router.classify("What would financing look like?", _deps())
    assert intent == "transaction.financing"


def test_price_parsing_variants():
    _, ent, _ = router.classify("show cars under KES 2,500,000", _deps())
    assert ent["max_price_kes"] == 2_500_000
