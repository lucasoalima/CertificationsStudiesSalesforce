"""A tiny persistent vector store (numpy matrix + JSONL metadata) with MMR retrieval.

For a corpus of study documents (thousands of chunks) brute-force cosine similarity is
fast enough and keeps the project free of heavy infrastructure. The interface mirrors
what a FAISS/Chroma/pgvector backend would expose, so it can be swapped later.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .embeddings import Embedder
from .schemas import Chunk, Retrieved


class VectorStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, embedder_name: str):
        assert len(chunks) == len(vectors)
        self.chunks = chunks
        self.vectors = vectors.astype(np.float32)
        self.embedder_name = embedder_name

    @classmethod
    def build(cls, chunks: list[Chunk], embedder: Embedder, batch: int = 64) -> "VectorStore":
        vecs = [embedder.embed([c.heading + "\n" + c.text for c in chunks[i : i + batch]]) for i in range(0, len(chunks), batch)]
        mat = np.vstack(vecs) if vecs else np.zeros((0, 1), dtype=np.float32)
        return cls(chunks, mat, embedder.name)

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "vectors.npy", self.vectors)
        with (folder / "chunks.jsonl").open("w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(c.model_dump_json() + "\n")
        (folder / "meta.json").write_text(json.dumps({"embedder": self.embedder_name, "n": len(self.chunks)}), encoding="utf-8")

    @classmethod
    def load(cls, folder: Path) -> "VectorStore":
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        chunks = [Chunk.model_validate_json(line) for line in (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
        return cls(chunks, np.load(folder / "vectors.npy"), meta["embedder"])

    def search(
        self,
        query_vec: np.ndarray,
        k: int = 6,
        cert: str | None = None,
        mmr_lambda: float = 0.7,
        candidates: int = 30,
    ) -> list[Retrieved]:
        """Top-k by cosine, re-ranked with Maximal Marginal Relevance to diversify context."""
        if not len(self.chunks):
            return []
        mask = np.array([cert is None or c.cert in (cert, None) for c in self.chunks])
        sims = self.vectors @ query_vec.astype(np.float32)
        sims = np.where(mask, sims, -np.inf)
        order = [int(i) for i in np.argsort(-sims)[:candidates] if np.isfinite(sims[i])]
        chosen: list[int] = []
        while order and len(chosen) < k:
            if not chosen:
                best = order[0]
            else:
                red = self.vectors[order] @ self.vectors[chosen].T
                score = mmr_lambda * sims[order] - (1 - mmr_lambda) * red.max(axis=1)
                best = order[int(np.argmax(score))]
            chosen.append(best)
            order.remove(best)
        return [Retrieved(chunk=self.chunks[i], score=float(sims[i])) for i in chosen]


class Retriever:
    def __init__(self, store: VectorStore, embedder: Embedder):
        if store.embedder_name != embedder.name:
            raise ValueError(
                f"index was built with '{store.embedder_name}' but the current embedder is '{embedder.name}'. Re-run ingest."
            )
        self.store, self.embedder = store, embedder

    def retrieve(self, query: str, k: int = 6, cert: str | None = None) -> list[Retrieved]:
        return self.store.search(self.embedder.embed([query])[0], k=k, cert=cert)
