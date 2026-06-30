"""In-memory ChromaDB RAG store using image-baked ONNX all-MiniLM-L6-v2.

Retrieval returns chunks with citable metadata (source id + title). The Knowledge
Agent may only assert claims supported by retrieved chunks; citations come from
this metadata, never the model's imagination.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..seed_data.faqs import KNOWLEDGE_DOCS

_COLLECTION = "carduka_kb"
logger = logging.getLogger(__name__)
@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    title: str
    category: str
    text: str
    score: float
    source_url: str | None = None


class RagStore:
    def __init__(self) -> None:
        self._collection = None
        self._ready = False

    def initialize(self) -> None:
        """Build the in-memory collection and embed the knowledge docs.

        Heavy (loads the embedding model) — runs in the background init task so
        /api/health can answer 503 immediately and flip to ready when done.
        """
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.Client()
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
                }
                for d in KNOWLEDGE_DOCS
            ],
        )
        self._collection = collection
        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    def retrieve(self, query: str, *, k: int = 3) -> list[RetrievedChunk]:
        if not self._ready or self._collection is None:
            return []
        try:
            res = self._collection.query(query_texts=[query], n_results=k)
        except Exception:
            # A transient embedding/backend failure (e.g. the macOS CoreML ONNX
            # provider) must degrade to a graceful "no sources" decline, never crash
            # the chat stream. Production (Linux/CPU) does not hit this path.
            logger.exception("RAG retrieval failed")
            return []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        chunks: list[RetrievedChunk] = []
        for i, source_id in enumerate(ids):
            meta = metas[i] or {}
            dist = dists[i] if i < len(dists) else 1.0
            chunks.append(
                RetrievedChunk(
                    source_id=source_id,
                    title=meta.get("title", source_id),
                    category=meta.get("category", "general"),
                    text=docs[i],
                    score=round(1.0 - float(dist), 3),
                    source_url=meta.get("source_url") or None,
                )
            )
        return chunks
