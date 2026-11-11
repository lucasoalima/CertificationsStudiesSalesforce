"""Independent verification of generated (or imported) questions.

Two signals, inspired by "LLM-as-a-judge" and RAG groundedness checks:
1. Blind solve: a solver model answers the question WITHOUT seeing the key; we check agreement.
2. Groundedness: is the correct option supported by the retrieved passages? Combines the
   solver's own support judgement with a lexical recall of the answer's key terms in the cited text.
"""
from __future__ import annotations

from .embeddings import tokenize
from .llm import LLM, LLMError, complete_json
from .prompts import SYSTEM_SOLVER, solver_prompt
from .schemas import Question, Retrieved, Verdict

LETTERS = "ABCDEF"


def _parse_letters(raw, n_opts: int) -> list[int]:
    vals = raw if isinstance(raw, list) else [raw]
    out = []
    for v in vals:
        if isinstance(v, int) and 0 <= v < n_opts:
            out.append(v)
        elif isinstance(v, str) and v.strip()[:1].upper() in LETTERS[:n_opts]:
            out.append(LETTERS.index(v.strip()[:1].upper()))
    return sorted(set(out))


def answer_recall(q: Question, passages: list[str]) -> float:
    """Share of the correct option's content tokens that appear in the supporting passages."""
    toks = set()
    for i in q.answers():
        toks |= set(tokenize(q.o[i]))
    if not toks:
        return 0.0
    ctx = set(tokenize(" ".join(passages)))
    return len(toks & ctx) / len(toks)


def verify_question(q: Question, ctx: list[Retrieved], solver: LLM, min_grounding: float = 0.6) -> Verdict:
    issues: list[str] = []
    try:
        r = complete_json(solver, solver_prompt(q, ctx), system=SYSTEM_SOLVER, max_tokens=800)
    except LLMError as e:
        return Verdict(question_id=q.id, solver_answer=[], agrees=False, grounded=False, grounding_score=0, issues=[f"solver failed: {e}"], status="review")
    ans = _parse_letters(r.get("answer"), len(q.o)) if isinstance(r, dict) else []
    agrees = ans == q.answers()
    by_id = {c.chunk.id: c.chunk.text for c in ctx}
    cited = [by_id[i] for i in (list(q.sources) + list(r.get("support_ids") or [])) if i in by_id] or list(by_id.values())
    recall = answer_recall(q, cited)
    supported = bool(r.get("supported")) if isinstance(r, dict) else False
    score = round(0.5 * float(supported) + 0.5 * recall, 3)
    grounded = score >= min_grounding
    ambiguous = bool(r.get("ambiguous")) if isinstance(r, dict) else False
    issues += [str(x) for x in (r.get("issues") or [])] if isinstance(r, dict) else []
    if not agrees:
        issues.append(f"solver chose {', '.join(LETTERS[i] for i in ans) or 'nothing'}; key is {', '.join(LETTERS[i] for i in q.answers())}")
    if agrees and grounded and not ambiguous:
        status = "accepted"
    elif not agrees and not grounded:
        status = "rejected"
    else:
        status = "review"
    return Verdict(
        question_id=q.id, solver_answer=ans, agrees=agrees, grounded=grounded,
        grounding_score=score, ambiguous=ambiguous, issues=issues, status=status,
    )
