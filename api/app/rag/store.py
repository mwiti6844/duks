"""Ephemeral file-backed ChromaDB RAG store using baked ONNX all-MiniLM-L6-v2.

Retrieval returns chunks with citable metadata (source id + title). The Knowledge
Agent may only assert claims supported by retrieved chunks; citations come from
this metadata, never the model's imagination.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from dataclasses import dataclass

from ..seed_data.faqs import KNOWLEDGE_DOCS

_COLLECTION = "carduka_kb"
logger = logging.getLogger(__name__)

_CATEGORY_TERMS = (
    ("dealer-finance", (
        "dealer finance", "dealer financing", "dealership", "stock financing",
        "stock finance", "motor dealer", "working capital",
    )),
    ("insurance", (
        "insurance", "insure", "motor cover", "vehicle cover", "premium",
        "third party", "comprehensive cover",
    )),
    ("trade-in", (
        "trade-in", "trade in", "trading in", "swap my car", "exchange my car",
        "exchange my vehicle", "existing vehicle for another",
    )),
    ("auctions", (
        "auction", "bidding", "bid increment", "reserve price", "highest bidder",
    )),
    ("financing", (
        "car loan", "vehicle loan", "financing", "finance a car", "repayment",
        "early settlement", "credit eligibility", "qualify for a car",
    )),
    ("policies", (
        "return window", "return policy", "inspection", "buyer protection",
        "escrow", "logbook", "payment", "service fee",
    )),
)

_CATEGORY_CONTEXT = {
    "dealer-finance": "motor dealership stock financing working capital application",
    "insurance": "motor vehicle insurance cover premium comprehensive third party",
    "trade-in": "trade in exchange current vehicle desired replacement offers",
    "auctions": "online vehicle auction bidding reserve price winning bidder",
    "financing": "vehicle financing car loan eligibility documents repayment term",
    "policies": "marketplace policy inspection return payment escrow logbook fees",
}


@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    title: str
    category: str
    text: str
    score: float
    source_url: str | None = None
    section: str | None = None
    document_version: str | None = None
    retrieved_at: str | None = None
    vector_score: float = 0.0
    lexical_score: float = 0.0


_STOP_WORDS = {
    "a", "an", "and", "are", "can", "car", "carduka", "do", "does", "for",
    "how", "i", "in", "is", "it", "me", "my", "of", "on", "the", "to",
    "vehicle", "what", "with", "work",
}


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _lexical_score(query: str, title: str, text: str) -> float:
    """Small-corpus keyword signal used alongside semantic similarity."""
    query_terms = _terms(query)
    if not query_terms:
        return 0.0
    title_terms = _terms(title)
    body_terms = _terms(text)
    matched = sum(
        2 if term in title_terms else 1
        for term in query_terms
        if term in body_terms or term in title_terms
    )
    return min(1.0, matched / max(1, len(query_terms)))


class RagStore:
    def __init__(self, path: str | None = None) -> None:
        # Chroma's pure in-memory SQLite is connection-local and fails when FastAPI
        # serves requests from different worker threads ("no such table: collections").
        # A unique /tmp directory remains ephemeral while sharing one SQLite file
        # safely across all request threads.
        self._path = path or os.getenv("CHROMA_PATH") or tempfile.mkdtemp(
            prefix="carduka-chroma-"
        )
        self._client = None
        self._collection = None
        self._ready = False
        # Last query-time failure (exception class + message). Surfaced in the
        # readiness probe's failure message (factory.py) so a broken retrieval
        # runtime names its cause instead of vanishing into a swallowed [] result.
        self._last_error: str | None = None

    def initialize(self) -> None:
        """Build the in-memory collection and embed the knowledge docs.

        Heavy (loads the embedding model) — runs in the background init task so
        /api/health can answer 503 immediately and flip to ready when done.
        """
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=self._path)
        # Chroma's ONNX MiniLM implementation avoids a multi-gigabyte PyTorch/CUDA
        # dependency while producing local semantic embeddings for this small corpus.
        # Pin the CPU execution provider: the macOS CoreML provider intermittently
        # returns degenerate embeddings for this model, which would make retrieval
        # nondeterministic. CPU is correct and stable on every platform (incl. Railway).
        try:
            embed_fn = embedding_functions.ONNXMiniLM_L6_V2(
                preferred_providers=["CPUExecutionProvider"]
            )
        except Exception:
            embed_fn = embedding_functions.DefaultEmbeddingFunction()
        # Fresh collection each boot (in-memory anyway).
        try:
            client.delete_collection(_COLLECTION)
        except Exception:
            pass
        collection = client.create_collection(
            name=_COLLECTION,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=[d["id"] for d in KNOWLEDGE_DOCS],
            documents=[d["text"] for d in KNOWLEDGE_DOCS],
            metadatas=[
                {
                    "title": d["title"],
                    "category": d["category"],
                    "source_url": d.get("source_url", ""),
                    "section": d.get("section", d["category"]),
                    "document_version": d.get("document_version", "demo-v1"),
                }
                for d in KNOWLEDGE_DOCS
            ],
        )
        # Keep the owning client alive for the collection lifetime; the request
        # threads all share this file-backed client/system.
        self._client = client
        self._collection = collection
        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @staticmethod
    def query_category(query: str) -> str | None:
        """Classify only known KB domains; unknown queries remain unfiltered."""
        text = " ".join(query.lower().replace("_", " ").split())
        for category, phrases in _CATEGORY_TERMS:
            if any(phrase in text for phrase in phrases):
                return category
        if re.search(r"\b(?:trade|trading|swap|exchange)\b", text) \
                and re.search(r"\b(?:car|vehicle|ride)\b", text):
            return "trade-in"
        if re.search(r"\b(?:cover|insured|policy premium)\b", text):
            return "insurance"
        if re.search(
            r"\b(?:fees?|charges?|handover|inspect(?:ed|ion)?|return(?:able|s|ed)?)\b",
            text,
        ):
            return "policies"
        return None

    def retrieve(self, query: str, *, k: int = 3) -> list[RetrievedChunk]:
        if not self._ready or self._collection is None:
            raise RuntimeError(
                "RAG store is unavailable after readiness "
                f"(ready={self._ready}, client={self._client is not None}, "
                f"collection={self._collection is not None})"
            )
        try:
            category = self.query_category(query)
            expanded_query = (
                f"{query}\nDomain context: {_CATEGORY_CONTEXT[category]}"
                if category else query
            )
            # The KB is deliberately tiny. Query the complete corpus, then filter
            # category metadata in Python. Chroma 0.5's HNSW metadata-filter path can
            # intermittently return an empty set in a long-running process even when
            # matching rows exist; full-corpus ranking is deterministic at this scale.
            res = self._collection.query(
                query_texts=[expanded_query],
                n_results=len(KNOWLEDGE_DOCS),
            )
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("RAG retrieval failed for query=%r", query)
            raise RuntimeError(f"RAG retrieval backend failed: {self._last_error}") from exc
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        candidates: list[RetrievedChunk] = []
        retrieved_at = datetime.now(UTC).isoformat()
        for i, source_id in enumerate(ids):
            meta = metas[i] or {}
            if category and meta.get("category") != category:
                continue
            dist = dists[i] if i < len(dists) else 1.0
            vector_score = max(-1.0, min(1.0, 1.0 - float(dist)))
            lexical_score = _lexical_score(query, meta.get("title", ""), docs[i])
            # Semantic similarity handles paraphrases; lexical overlap rewards exact
            # policy/product terms and makes retrieval less dependent on either alone.
            hybrid_score = (0.75 * vector_score) + (0.25 * lexical_score)
            candidates.append(
                RetrievedChunk(
                    source_id=source_id,
                    title=meta.get("title", source_id),
                    category=meta.get("category", "general"),
                    text=docs[i],
                    score=round(hybrid_score, 3),
                    source_url=meta.get("source_url") or None,
                    section=meta.get("section") or None,
                    document_version=meta.get("document_version") or None,
                    retrieved_at=retrieved_at,
                    vector_score=round(vector_score, 3),
                    lexical_score=round(lexical_score, 3),
                )
            )
        # Explicit reranking after broad retrieval. Stable source_id tie-breaking
        # makes tests and traces reproducible.
        candidates.sort(key=lambda item: (-item.score, item.source_id))
        chunks = candidates[:k]
        if category and not candidates:
            raise RuntimeError(
                f"RAG returned no rows for known category {category!r}"
            )
        return chunks
