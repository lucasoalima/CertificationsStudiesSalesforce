"""Wires settings, index, embedder and LLMs together for the CLI and the API."""
from __future__ import annotations

from functools import lru_cache

from .config import Settings, get_settings, load_outlines
from .embeddings import Embedder, make_embedder
from .ingest import load_corpus
from .llm import LLM, make_llm
from .store import Retriever, VectorStore


class Service:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.outlines = load_outlines()
        self._embedder: Embedder | None = None
        self._retriever: Retriever | None = None

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = make_embedder(self.settings.embedder, self.settings)
        return self._embedder

    def ingest(self) -> dict:
        s = self.settings
        chunks = load_corpus(s.docs_dir, set(self.outlines), s.chunk_chars, s.chunk_overlap)
        if not chunks:
            raise RuntimeError(f"no documents found in {s.docs_dir}")
        store = VectorStore.build(chunks, self.embedder)
        store.save(s.index_dir)
        self._retriever = None
        by_cert: dict[str, int] = {}
        for c in chunks:
            by_cert[c.cert or "(geral)"] = by_cert.get(c.cert or "(geral)", 0) + 1
        return {"chunks": len(chunks), "docs": len({c.doc for c in chunks}), "by_cert": by_cert, "embedder": self.embedder.name}

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            if not (self.settings.index_dir / "meta.json").exists():
                raise RuntimeError("index not found: run `python -m qgen ingest` first")
            self._retriever = Retriever(VectorStore.load(self.settings.index_dir), self.embedder)
        return self._retriever

    def llm(self, spec: str | None = None) -> LLM:
        return make_llm(spec, self.settings)


@lru_cache
def get_service() -> Service:
    return Service()
