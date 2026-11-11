"""End-to-end orchestration: retrieve → generate → validate → verify → dedupe."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from .dedupe import dedupe
from .embeddings import Embedder
from .llm import LLM, LLMError, complete_json
from .prompts import PROMPT_VERSION, SYSTEM_WRITER, completion_prompt, generation_prompt
from .schemas import ExamOutline, Question, Retrieved, Verdict
from .store import Retriever
from .verify import _parse_letters, verify_question


@dataclass
class RunStats:
    requested: int = 0
    raw: int = 0
    schema_valid: int = 0
    invalid_reasons: list[str] = field(default_factory=list)
    citations_valid: int = 0
    duplicates: int = 0
    accepted: int = 0
    review: int = 0
    rejected: int = 0
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RunResult:
    questions: list[Question]
    verdicts: dict[str, Verdict]
    stats: RunStats
    context: list[Retrieved]


def section_query(outline: ExamOutline, section_name: str, focus: str = "", topics: str = "") -> str:
    """Retrieval query for a section. The cert name is left out on purpose: the cert filter already
    scopes the search, and generic words like "Data 360" would pull unrelated chunks."""
    return f"{section_name}: {topics}. {focus}".strip()


def _norm_answer(raw, n_opts: int):
    """Accept 0 / "B" / ["A","C"] / [0,2] from the model; None if unusable."""
    idx = _parse_letters(raw, n_opts)
    return None if not idx else (idx[0] if len(idx) == 1 and not isinstance(raw, list) else idx)


def _qid(cert: str, text: str) -> str:
    return f"{cert}-" + hashlib.sha1(text.encode()).hexdigest()[:10]


def generate(
    *,
    outline: ExamOutline,
    section_key: str,
    n: int,
    retriever: Retriever,
    writer: LLM,
    solver: LLM | None,
    embedder: Embedder,
    existing: list[Question] | None = None,
    top_k: int = 6,
    focus: str = "",
    min_grounding: float = 0.6,
    dup_threshold: float = 0.88,
    keep: str = "accepted",  # accepted | review | all
) -> RunResult:
    t0 = time.perf_counter()
    existing = existing or []
    section = outline.section(section_key)
    stats = RunStats(requested=n)
    ctx = retriever.retrieve(section_query(outline, section.name, focus, section.topics), k=top_k, cert=outline.id)
    if not ctx:
        raise LLMError("no context retrieved: ingest documents for this certification first")
    avoid = [q.q for q in existing if q.s == section_key]
    raw = complete_json(writer, generation_prompt(outline, section, ctx, n, avoid), system=SYSTEM_WRITER, max_tokens=6000)
    raw = raw if isinstance(raw, list) else [raw]
    stats.raw = len(raw)
    ctx_ids = {c.chunk.id for c in ctx}
    questions: list[Question] = []
    for item in raw:
        try:
            q = Question(
                q=str(item.get("q", "")).strip(), o=item.get("o") or [], a=_norm_answer(item.get("a"), len(item.get("o") or [])), e=str(item.get("e", "")),
                s=section.k, t=section.name, cert=outline.id, src="rag",
                sources=[s for s in (item.get("sources") or []) if isinstance(s, str)],
                meta={"writer": writer.name, "prompt": PROMPT_VERSION, "context": sorted(ctx_ids)},
            )
            if not q.q:
                raise ValueError("empty stem")
            if q.a is None:
                raise ValueError("missing answer key")
        except (ValidationError, ValueError, TypeError, AttributeError) as e:
            stats.invalid_reasons.append(str(e).splitlines()[0][:120])
            continue
        q.id = _qid(outline.id, q.q)
        if q.sources and set(q.sources) <= ctx_ids:
            stats.citations_valid += 1
        questions.append(q)
    stats.schema_valid = len(questions)

    dd = dedupe(questions, existing, embedder, dup_threshold)
    stats.duplicates = len(dd.dropped)
    questions = dd.kept

    verdicts: dict[str, Verdict] = {}
    if solver is not None:
        for q in questions:
            v = verify_question(q, ctx, solver, min_grounding)
            verdicts[q.id] = v
            q.meta["verdict"] = v.status
            setattr(stats, v.status, getattr(stats, v.status) + 1)
    allowed = {"accepted": {"accepted"}, "review": {"accepted", "review"}, "all": {"accepted", "review", "rejected"}}[keep]
    if solver is not None:
        questions = [q for q in questions if verdicts[q.id].status in allowed]
    stats.seconds = round(time.perf_counter() - t0, 2)
    return RunResult(questions, verdicts, stats, ctx)


def complete_keys(
    *, outline: ExamOutline, items: list[Question], retriever: Retriever, llm: LLM, top_k: int = 4, batch: int = 6
) -> list[tuple[Question, str]]:
    """Fill in answer key, explanation and section for imported questions that have none."""
    out: list[tuple[Question, str]] = []
    for i in range(0, len(items), batch):
        part = items[i : i + batch]
        ctxs = [retriever.retrieve(q.q + " " + " ".join(q.o), k=top_k, cert=outline.id) for q in part]
        res = complete_json(llm, completion_prompt(outline, part, ctxs), max_tokens=3000)
        for q, r, ctx in zip(part, res if isinstance(res, list) else [], ctxs):
            ans = _parse_letters(r.get("a"), len(q.o)) if isinstance(r, dict) else []
            if not ans:
                continue
            sec = r.get("s") if r.get("s") in {s.k for s in outline.sections} else ""
            q2 = q.model_copy(update={
                "a": ans if len(ans) > 1 else ans[0], "e": q.e or str(r.get("e", "")), "s": q.s or sec,
                "t": q.t or (outline.section(sec).name if sec else ""), "sources": [c.chunk.id for c in ctx],
            })
            out.append((q2, str(r.get("confidence", "medium"))))
    return out
