"""Near-duplicate detection: exact match on normalised text, then semantic similarity."""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .embeddings import Embedder
from .schemas import Question


def normalise(text: str) -> str:
    text = text.lower().replace("data cloud", "data 360")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def signature(q: Question) -> str:
    """Stem + correct option(s): two questions that test the same fact with the same key collide."""
    return q.q + " || " + " | ".join(q.o[i] for i in q.answers())


@dataclass
class DedupeResult:
    kept: list[Question]
    dropped: list[tuple[Question, str, float]]  # (question, id it duplicates, similarity)


def dedupe(new: list[Question], existing: list[Question], embedder: Embedder, threshold: float = 0.88) -> DedupeResult:
    kept: list[Question] = []
    dropped: list[tuple[Question, str, float]] = []
    seen_text = {normalise(q.q): q.id for q in existing}
    pool = list(existing)
    pool_vecs = embedder.embed([signature(q) for q in pool]) if pool else np.zeros((0, 1), dtype=np.float32)
    for q in new:
        key = normalise(q.q)
        if key in seen_text:
            dropped.append((q, seen_text[key], 1.0))
            continue
        v = embedder.embed([signature(q)])[0]
        if len(pool):
            sims = pool_vecs @ v
            j = int(np.argmax(sims))
            if sims[j] >= threshold:
                dropped.append((q, pool[j].id, float(sims[j])))
                continue
        kept.append(q)
        seen_text[key] = q.id
        pool.append(q)
        pool_vecs = np.vstack([pool_vecs, v[None, :]]) if len(pool_vecs) and pool_vecs.shape[1] == v.shape[0] else v[None, :]
    return DedupeResult(kept, dropped)
