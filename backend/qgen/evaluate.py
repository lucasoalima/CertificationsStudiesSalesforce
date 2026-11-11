"""Experiments: retrieval quality per embedder and generation quality per LLM.

Retrieval  -> Recall@k and MRR over a small labelled query set (data/eval/retrieval.jsonl).
Generation -> schema validity, citation validity, duplicate rate, blind-solve agreement,
              groundedness, ambiguity, acceptance, answer-position bias, "longest option is
              correct" bias, tokens and latency.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .embeddings import Embedder
from .llm import LLM, LLMError
from .pipeline import generate
from .schemas import Chunk, ExamOutline, Question
from .store import Retriever, VectorStore


# ---------------- retrieval ----------------
def load_retrieval_set(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _is_relevant(chunk: Chunk, item: dict) -> bool:
    docs = item.get("relevant_docs") or []
    heads = [h.lower() for h in item.get("relevant_headings") or []]
    return (not docs or any(chunk.doc.endswith(d) for d in docs)) and (not heads or chunk.heading.split(" > ")[-1].lower() in heads)


def eval_retrieval(chunks: list[Chunk], embedder: Embedder, items: list[dict], ks=(1, 3, 5)) -> dict:
    store = VectorStore.build(chunks, embedder)
    ret = Retriever(store, embedder)
    kmax = max(ks)
    hits = {k: 0 for k in ks}
    rr = 0.0
    for it in items:
        res = ret.store.search(embedder.embed([it["query"]])[0], k=kmax, cert=it.get("cert"), mmr_lambda=1.0)
        rank = next((i for i, r in enumerate(res, 1) if _is_relevant(r.chunk, it)), None)
        for k in ks:
            hits[k] += int(rank is not None and rank <= k)
        rr += 1 / rank if rank else 0
    n = max(len(items), 1)
    return {"embedder": embedder.name, "n": len(items), **{f"recall@{k}": round(hits[k] / n, 3) for k in ks}, "mrr": round(rr / n, 3)}


# ---------------- generation ----------------
@dataclass
class GenMetrics:
    model: str
    judge: str
    sections: int = 0
    requested: int = 0
    raw: int = 0
    valid: int = 0
    citations_valid: int = 0
    duplicates: int = 0
    verified: int = 0
    agree: int = 0
    grounded: int = 0
    ambiguous: int = 0
    accepted: int = 0
    longest_is_correct: int = 0
    single_answer: int = 0
    positions: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0

    def summary(self) -> dict:
        r = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
        pos_total = sum(self.positions.values())
        k = 4
        entropy = -sum((c / pos_total) * math.log(c / pos_total, k) for c in self.positions.values()) if pos_total else None
        return {
            "model": self.model, "judge": self.judge, "sections": self.sections, "requested": self.requested, "raw": self.raw,
            "schema_valid_rate": r(self.valid, self.raw), "citation_valid_rate": r(self.citations_valid, self.valid),
            "duplicate_rate": r(self.duplicates, self.valid), "agreement_rate": r(self.agree, self.verified),
            "grounded_rate": r(self.grounded, self.verified), "ambiguous_rate": r(self.ambiguous, self.verified),
            "acceptance_rate": r(self.accepted, self.verified), "longest_option_correct_rate": r(self.longest_is_correct, self.single_answer),
            "answer_position_entropy": round(entropy, 3) if entropy is not None else None,
            "answer_positions": dict(sorted(self.positions.items())), "seconds": round(self.seconds, 1),
            "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "errors": self.errors[:10],
        }


def _longest_correct(q: Question) -> bool:
    lens = [len(o) for o in q.o]
    return lens[q.answers()[0]] == max(lens) and lens.count(max(lens)) == 1


def eval_generation(
    *, outline: ExamOutline, sections: list[str], n_per_section: int, retriever: Retriever, writer: LLM, judge: LLM,
    embedder: Embedder, top_k: int = 6, min_grounding: float = 0.6, dup_threshold: float = 0.88,
) -> tuple[GenMetrics, list[Question]]:
    m = GenMetrics(model=writer.name, judge=judge.name)
    produced: list[Question] = []
    t0 = time.perf_counter()
    for sk in sections:
        m.sections += 1
        m.requested += n_per_section
        try:
            res = generate(
                outline=outline, section_key=sk, n=n_per_section, retriever=retriever, writer=writer, solver=judge,
                embedder=embedder, existing=produced, top_k=top_k, min_grounding=min_grounding, dup_threshold=dup_threshold, keep="all",
            )
        except LLMError as e:
            m.errors.append(f"{sk}: {e}")
            continue
        st = res.stats
        m.raw += st.raw
        m.valid += st.schema_valid
        m.citations_valid += st.citations_valid
        m.duplicates += st.duplicates
        for q in res.questions:
            v = res.verdicts.get(q.id)
            if v:
                m.verified += 1
                m.agree += v.agrees
                m.grounded += v.grounded
                m.ambiguous += v.ambiguous
                m.accepted += v.status == "accepted"
            if len(q.answers()) == 1:
                m.single_answer += 1
                m.longest_is_correct += _longest_correct(q)
                m.positions["ABCDEF"[q.answers()[0]]] += 1
        produced += res.questions
    m.seconds = time.perf_counter() - t0
    m.tokens_in = writer.usage.input_tokens + (judge.usage.input_tokens if judge is not writer else 0)
    m.tokens_out = writer.usage.output_tokens + (judge.usage.output_tokens if judge is not writer else 0)
    return m, produced


# ---------------- report ----------------
def write_report(folder: Path, title: str, retrieval: list[dict], generation: list[dict], notes: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (folder / f"eval-{stamp}.json").write_text(json.dumps({"retrieval": retrieval, "generation": generation}, indent=2), encoding="utf-8")
    lines = [f"# {title}", "", f"_Gerado em {time.strftime('%Y-%m-%d %H:%M')}_", ""]
    if notes:
        lines += [notes, ""]
    if retrieval:
        ks = [k for k in retrieval[0] if k.startswith("recall@")]
        lines += ["## Retrieval", "", "| Embedder | n | " + " | ".join(ks) + " | MRR |", "|---|---|" + "---|" * len(ks) + "---|"]
        lines += [f"| {r['embedder']} | {r['n']} | " + " | ".join(str(r[k]) for k in ks) + f" | {r['mrr']} |" for r in retrieval]
        lines.append("")
    if generation:
        cols = ["schema_valid_rate", "citation_valid_rate", "duplicate_rate", "agreement_rate", "grounded_rate", "ambiguous_rate",
                "acceptance_rate", "longest_option_correct_rate", "answer_position_entropy", "seconds", "tokens_in", "tokens_out"]
        lines += ["## Geração", "", "| Modelo | Juiz | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
        lines += [f"| {g['model']} | {g['judge']} | " + " | ".join("" if g[c] is None else str(g[c]) for c in cols) + " |" for g in generation]
        lines += ["", "**Como ler:** `agreement_rate` = o juiz, sem ver o gabarito, chegou à mesma resposta; `grounded_rate` = a resposta correta está "
                  "sustentada pelos trechos recuperados; `longest_option_correct_rate` alto (≫ 0.25) indica o viés clássico de LLM de deixar a "
                  "alternativa certa mais longa; `answer_position_entropy` perto de 1 = gabarito bem distribuído entre A–D.", ""]
        for g in generation:
            if g["errors"]:
                lines += [f"Erros ({g['model']}): " + "; ".join(g["errors"]), ""]
    path = folder / f"eval-{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
