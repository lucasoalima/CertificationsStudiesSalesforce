"""HTTP API used by the web app (Certificações → ✨ Gerar perguntas → backend).

Run:  uvicorn qgen.api:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .bank import to_app
from .llm import LLMError
from .pipeline import complete_keys, generate
from .schemas import Question
from .service import get_service
from .verify import verify_question

app = FastAPI(title="Salesforce Cert Studies — question generation API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenerateIn(BaseModel):
    cert: str
    section: str
    n: int = Field(5, ge=1, le=20)
    provider: str | None = Field(None, description="anthropic | ollama | anthropic:<model> | ollama:<model>")
    judge: str | None = Field(None, description="LLM used to verify; defaults to the same as provider")
    verify: bool = True
    keep: str = Field("review", pattern="^(accepted|review|all)$")
    existing: list[dict] = Field(default_factory=list, description="Questions already in the user's bank (for dedupe)")


class VerifyIn(BaseModel):
    cert: str
    questions: list[dict]
    judge: str | None = None


def _outline(cert: str):
    svc = get_service()
    if cert not in svc.outlines:
        raise HTTPException(404, f"unknown cert '{cert}'")
    return svc.outlines[cert]


def _to_questions(items: list[dict], cert: str) -> list[Question]:
    out = []
    for i, x in enumerate(items):
        try:
            out.append(Question(id=str(x.get("id") or f"in-{i}"), q=x["q"], o=x["o"], a=x.get("a"), e=x.get("e", ""), s=x.get("s", ""), t=x.get("t", ""), cert=cert, src=x.get("src", "import")))
        except Exception:  # noqa: BLE001 - skip malformed items from the client
            continue
    return out


@app.get("/health")
def health():
    svc = get_service()
    try:
        n = len(svc.retriever.store.chunks)
    except RuntimeError:
        n = 0
    return {"ok": True, "chunks": n, "embedder": svc.settings.embedder, "provider": svc.settings.provider}


@app.get("/outlines")
def outlines():
    return [o.model_dump() for o in get_service().outlines.values()]


@app.post("/generate")
def generate_endpoint(body: GenerateIn):
    svc = get_service()
    outline = _outline(body.cert)
    try:
        writer = svc.llm(body.provider)
        judge = (svc.llm(body.judge) if body.judge else writer) if body.verify else None
        res = generate(
            outline=outline, section_key=body.section, n=body.n, retriever=svc.retriever, writer=writer, solver=judge,
            embedder=svc.embedder, existing=_to_questions(body.existing, body.cert), top_k=svc.settings.top_k,
            min_grounding=svc.settings.min_grounding, dup_threshold=svc.settings.dup_threshold, keep=body.keep,
        )
    except (LLMError, RuntimeError, KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {
        "questions": [to_app(q) for q in res.questions],
        "verdicts": {k: v.model_dump() for k, v in res.verdicts.items()},
        "stats": res.stats.as_dict(),
        "context": [{"id": r.chunk.id, "doc": r.chunk.doc, "heading": r.chunk.heading, "score": round(r.score, 3)} for r in res.context],
    }


@app.post("/verify")
def verify_endpoint(body: VerifyIn):
    svc = get_service()
    _outline(body.cert)
    try:
        judge = svc.llm(body.judge)
        qs = [q for q in _to_questions(body.questions, body.cert) if q.a is not None]
        out = []
        for q in qs:
            ctx = svc.retriever.retrieve(q.q + " " + " ".join(q.o), k=svc.settings.top_k, cert=body.cert)
            out.append(verify_question(q, ctx, judge, svc.settings.min_grounding).model_dump())
    except (LLMError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e
    return {"verdicts": out}


@app.post("/complete")
def complete_endpoint(body: VerifyIn):
    svc = get_service()
    outline = _outline(body.cert)
    try:
        items = [q for q in _to_questions(body.questions, body.cert) if q.a is None]
        done = complete_keys(outline=outline, items=items, retriever=svc.retriever, llm=svc.llm(body.judge), top_k=svc.settings.top_k)
    except (LLMError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e
    return {"questions": [dict(to_app(q), confidence=c) for q, c in done]}
