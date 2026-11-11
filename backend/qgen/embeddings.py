"""Text embedders behind one small interface.

- HashingEmbedder: dependency-free baseline (hashed word + bigram features, TF weighting,
  L2-normalised). Works offline and in tests; good lexical recall, no semantics.
- OllamaEmbedder: local semantic embeddings (e.g. nomic-embed-text) through Ollama.
- SentenceTransformerEmbedder: semantic embeddings via sentence-transformers (optional install).

Comparing them is one of the experiments in the evaluation report.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an and are as at be by can for from has have how in is it its of on or that the this to was what when which who will with "
    "de do da dos das e em o os as um uma para por com que no na nos nas se ao".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 2048):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _idx(self, tok: str) -> tuple[int, float]:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        return h % self.dim, (1.0 if (h >> 64) & 1 else -1.0)

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            toks = tokenize(text)
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
            counts: dict[str, int] = {}
            for f in feats:
                counts[f] = counts.get(f, 0) + 1
            for f, c in counts.items():
                i, sign = self._idx(f)
                out[row, i] += sign * (1 + math.log(c))
            n = np.linalg.norm(out[row])
            if n:
                out[row] /= n
        return out


class OllamaEmbedder:
    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        self.name = f"ollama-{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        import httpx

        r = httpx.post(f"{self.url}/api/embed", json={"model": self.model, "input": texts}, timeout=120)
        r.raise_for_status()
        arr = np.asarray(r.json()["embeddings"], dtype=np.float32)
        return arr / np.clip(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9, None)


class SentenceTransformerEmbedder:
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self._m = SentenceTransformer(model)
        self.name = f"st-{model.split('/')[-1]}"

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._m.encode(texts, normalize_embeddings=True), dtype=np.float32)


def make_embedder(kind: str, settings) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    if kind == "ollama":
        return OllamaEmbedder(settings.ollama_url, settings.ollama_embed_model)
    if kind in {"st", "sentence-transformers"}:
        return SentenceTransformerEmbedder(settings.st_model)
    raise ValueError(f"unknown embedder '{kind}' (use hashing | ollama | st)")
