"""Prompt templates. Kept in one place so prompt variants can be versioned and compared."""
from __future__ import annotations

from .schemas import ExamOutline, ExamSection, Question, Retrieved

PROMPT_VERSION = "v1"

SYSTEM_WRITER = (
    "You are an experienced Salesforce instructor who writes certification practice questions. "
    "You only use facts stated in the provided CONTEXT. You reply with JSON only."
)

SYSTEM_SOLVER = (
    "You are a careful Salesforce expert taking a certification exam. "
    "Answer using the provided CONTEXT. You reply with JSON only."
)


def format_context(ctx: list[Retrieved]) -> str:
    return "\n\n".join(f"[{r.chunk.id}] ({r.chunk.doc} > {r.chunk.heading})\n{r.chunk.text}" for r in ctx)


def generation_prompt(outline: ExamOutline, section: ExamSection, ctx: list[Retrieved], n: int, avoid: list[str], lang_expl: str = "Brazilian Portuguese") -> str:
    avoid_txt = "\n".join(f"- {a[:140]}" for a in avoid[-20:]) or "(none)"
    return f"""Write {n} ORIGINAL multiple-choice practice questions for the Salesforce Certified {outline.name} exam ({outline.code}), section "{section.name}".

Rules:
- Every fact needed to answer MUST be supported by the CONTEXT below. Do not use outside knowledge for the correct answer.
- Real exam style: a short business scenario with a fictional company (Northern Trail Outfitters, Cumulus Financial, Cloud Kicks, Universal Containers), then the question.
- Exactly 4 options, exactly one correct, plausible distractors (real features used in the wrong situation). No "all/none of the above".
- One concept per question; do not repeat these existing questions:
{avoid_txt}
- "e": explanation in {lang_expl}, 2-4 sentences, product names in English: why the correct option is right and why the most tempting wrong option is wrong. Refer to options by content, never by letter.
- "sources": the ids (in square brackets) of the context passages that support the answer.

CONTEXT:
{format_context(ctx)}

Reply with ONLY a JSON array:
[{{"q": "question in English", "o": ["...", "...", "...", "..."], "a": 0, "e": "explicação", "sources": ["chunk-id"]}}]"""


def solver_prompt(q: Question, ctx: list[Retrieved]) -> str:
    letters = "ABCDEF"
    opts = "\n".join(f"{letters[i]}) {o}" for i, o in enumerate(q.o))
    n = len(q.answers())
    return f"""Answer this certification question. Choose exactly {n} option{'s' if n > 1 else ''}.
Base your answer on the CONTEXT. Then judge the question itself.

CONTEXT:
{format_context(ctx)}

QUESTION:
{q.q}
{opts}

Reply with ONLY JSON:
{{"answer": ["B"], "supported": true, "support_ids": ["chunk-id"], "ambiguous": false, "issues": ["short notes about factual errors, two defensible answers, or unclear wording; empty if none"]}}
- "supported": true only if the CONTEXT states the facts needed to pick the answer.
- "ambiguous": true if more than {n} option{'s are' if n > 1 else ' is'} defensible."""


def completion_prompt(outline: ExamOutline, items: list[Question], ctx_by_item: list[list[Retrieved]]) -> str:
    """For imported questions without an answer key: decide the key and explain, grounded in context."""
    letters = "ABCDEF"
    blocks = []
    for i, (q, ctx) in enumerate(zip(items, ctx_by_item), 1):
        opts = "\n".join(f"{letters[j]}) {o}" for j, o in enumerate(q.o))
        blocks.append(f"### Q{i}\nCONTEXT:\n{format_context(ctx)}\n\nQUESTION:\n{q.q}\n{opts}")
    secs = "; ".join(f"{s.k} = {s.name}" for s in outline.sections)
    return f"""You review practice questions for the Salesforce Certified {outline.name} exam. For each question decide the correct answer
(use its CONTEXT first; questions that say "Choose 2/3" need that many answers), write a 2-3 sentence explanation in Brazilian Portuguese
(product names in English, refer to options by content), and classify it into one exam section: {secs}.

{chr(10).join(blocks)}

Reply with ONLY a JSON array in the same order: [{{"a": ["B"], "e": "explicação", "s": "section key", "confidence": "high|medium|low"}}]"""
