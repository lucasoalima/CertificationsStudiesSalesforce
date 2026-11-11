"""Command-line interface.

    python -m qgen ingest
    python -m qgen search "identity resolution match rules" --cert d360
    python -m qgen generate --cert d360 --section ir -n 5 [--provider ollama] [--judge anthropic]
    python -m qgen verify  --cert d360 --bank meu-banco.json
    python -m qgen complete --cert d360 --bank sem-gabarito.json
    python -m qgen dedupe  --bank meu-banco.json
    python -m qgen eval    --cert d360 --models anthropic ollama:llama3.1:8b --judge anthropic -n 3
    python -m qgen eval-retrieval --embedders hashing ollama
    python -m qgen serve
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .bank import load_bank, save_app_json, to_app
from .config import ROOT
from .dedupe import dedupe
from .embeddings import make_embedder
from .evaluate import eval_generation, eval_retrieval, load_retrieval_set, write_report
from .ingest import load_corpus
from .llm import LLMError
from .pipeline import complete_keys, generate
from .service import Service
from .verify import verify_question


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_ingest(svc: Service, a) -> None:
    _p(svc.ingest())


def cmd_search(svc: Service, a) -> None:
    for r in svc.retriever.retrieve(a.query, k=a.k, cert=a.cert):
        print(f"{r.score:.3f}  [{r.chunk.id}] {r.chunk.doc} > {r.chunk.heading}\n       {r.chunk.text[:160].replace(chr(10), ' ')}…")


def cmd_generate(svc: Service, a) -> None:
    outline = svc.outlines[a.cert]
    existing, _ = load_bank(Path(a.bank), a.cert) if a.bank else ([], [])
    writer = svc.llm(a.provider)
    judge = None if a.no_verify else (svc.llm(a.judge) if a.judge else writer)
    sections = [s.k for s in outline.sections] if a.section == "all" else [a.section]
    out = []
    for sk in sections:
        res = generate(outline=outline, section_key=sk, n=a.n, retriever=svc.retriever, writer=writer, solver=judge, embedder=svc.embedder,
                       existing=existing + out, top_k=svc.settings.top_k, min_grounding=svc.settings.min_grounding,
                       dup_threshold=svc.settings.dup_threshold, keep=a.keep)
        print(f"[{sk}] " + json.dumps(res.stats.as_dict(), ensure_ascii=False), file=sys.stderr)
        out += res.questions
    path = Path(a.out or svc.settings.out_dir / f"{a.cert}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    save_app_json(out, path)
    print(f"{len(out)} questões salvas em {path} (importe no app: Certificações → 📥 Importar questões)", file=sys.stderr)


def cmd_verify(svc: Service, a) -> None:
    qs, errs = load_bank(Path(a.bank), a.cert)
    judge = svc.llm(a.judge)
    rows = []
    for q in [q for q in qs if q.a is not None]:
        ctx = svc.retriever.retrieve(q.q + " " + " ".join(q.o), k=svc.settings.top_k, cert=a.cert)
        v = verify_question(q, ctx, judge, svc.settings.min_grounding)
        rows.append({"id": q.id, "status": v.status, "agrees": v.agrees, "grounding": v.grounding_score, "issues": v.issues, "q": q.q[:120]})
    summary = {s: sum(r["status"] == s for r in rows) for s in ("accepted", "review", "rejected")}
    report = {"summary": summary, "parse_errors": errs, "items": rows}
    path = Path(a.out or svc.settings.reports_dir / f"verify-{a.cert}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _p(summary)
    print(f"relatório: {path}", file=sys.stderr)


def cmd_complete(svc: Service, a) -> None:
    outline = svc.outlines[a.cert]
    qs, _ = load_bank(Path(a.bank), a.cert)
    todo = [q for q in qs if q.a is None]
    done = complete_keys(outline=outline, items=todo, retriever=svc.retriever, llm=svc.llm(a.judge), top_k=svc.settings.top_k)
    path = Path(a.out or Path(a.bank).with_suffix(".completo.json"))
    save_app_json([q for q in qs if q.a is not None] + [q for q, _ in done], path)
    print(f"{len(done)}/{len(todo)} questões completadas → {path}", file=sys.stderr)


def cmd_dedupe(svc: Service, a) -> None:
    qs, _ = load_bank(Path(a.bank))
    with_key = [q for q in qs if q.a is not None]
    res = dedupe(with_key, [], svc.embedder, a.threshold)
    for q, other, sim in res.dropped:
        print(f"duplicada ({sim:.2f}) de {other}: {q.q[:100]}")
    path = Path(a.out or Path(a.bank).with_suffix(".dedup.json"))
    path.write_text(json.dumps([to_app(q) for q in res.kept], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(with_key)} → {len(res.kept)} questões ({len(res.dropped)} duplicadas) → {path}", file=sys.stderr)


def cmd_eval(svc: Service, a) -> None:
    outline = svc.outlines[a.cert]
    sections = [s.k for s in outline.sections] if not a.sections else a.sections
    gen = []
    for spec in a.models:
        writer = svc.llm(spec)
        judge = svc.llm(a.judge) if a.judge else writer
        try:
            m, _ = eval_generation(outline=outline, sections=sections, n_per_section=a.n, retriever=svc.retriever, writer=writer, judge=judge,
                                   embedder=svc.embedder, top_k=svc.settings.top_k, min_grounding=svc.settings.min_grounding,
                                   dup_threshold=svc.settings.dup_threshold)
            gen.append(m.summary())
        except LLMError as e:
            print(f"{spec}: {e}", file=sys.stderr)
    path = write_report(svc.settings.reports_dir, f"Avaliação de geração — {outline.name}", [], gen,
                        notes=f"Seções: {', '.join(sections)} · {a.n} questões por seção · juiz: {a.judge or 'o próprio modelo'}")
    print(path.read_text(encoding="utf-8"))


def cmd_eval_retrieval(svc: Service, a) -> None:
    items = load_retrieval_set(Path(a.set))
    chunks = load_corpus(svc.settings.docs_dir, set(svc.outlines), svc.settings.chunk_chars, svc.settings.chunk_overlap)
    rows = [eval_retrieval(chunks, make_embedder(k, svc.settings), items) for k in a.embedders]
    path = write_report(svc.settings.reports_dir, "Avaliação de retrieval", rows, [], notes=f"Conjunto: {a.set} ({len(items)} consultas), {len(chunks)} chunks")
    print(path.read_text(encoding="utf-8"))


def cmd_serve(svc: Service, a) -> None:
    import uvicorn

    uvicorn.run("qgen.api:app", host=a.host, port=a.port, reload=False)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="qgen", description="RAG question generation & verification for Salesforce certifications")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ingest", help="index documents from data/docs")
    s = sub.add_parser("search", help="query the index")
    s.add_argument("query"); s.add_argument("--cert"); s.add_argument("-k", type=int, default=5)

    g = sub.add_parser("generate", help="generate grounded questions")
    g.add_argument("--cert", required=True); g.add_argument("--section", required=True, help="section key or 'all'")
    g.add_argument("-n", type=int, default=5); g.add_argument("--provider"); g.add_argument("--judge")
    g.add_argument("--no-verify", action="store_true"); g.add_argument("--keep", default="review", choices=["accepted", "review", "all"])
    g.add_argument("--bank", help="existing bank (app JSON) for dedupe"); g.add_argument("--out")

    v = sub.add_parser("verify", help="verify an existing bank (answer key + groundedness)")
    v.add_argument("--cert", required=True); v.add_argument("--bank", required=True); v.add_argument("--judge"); v.add_argument("--out")

    c = sub.add_parser("complete", help="fill in missing answer keys")
    c.add_argument("--cert", required=True); c.add_argument("--bank", required=True); c.add_argument("--judge"); c.add_argument("--out")

    d = sub.add_parser("dedupe", help="remove near-duplicate questions from a bank")
    d.add_argument("--bank", required=True); d.add_argument("--threshold", type=float, default=0.88); d.add_argument("--out")

    e = sub.add_parser("eval", help="compare LLMs on generation quality")
    e.add_argument("--cert", required=True); e.add_argument("--models", nargs="+", required=True); e.add_argument("--judge")
    e.add_argument("--sections", nargs="*"); e.add_argument("-n", type=int, default=3)

    r = sub.add_parser("eval-retrieval", help="compare embedders on Recall@k / MRR")
    r.add_argument("--embedders", nargs="+", default=["hashing"]); r.add_argument("--set", default=str(ROOT / "data" / "eval" / "retrieval.jsonl"))

    sv = sub.add_parser("serve", help="run the HTTP API"); sv.add_argument("--host", default="127.0.0.1"); sv.add_argument("--port", type=int, default=8000)

    a = ap.parse_args(argv)
    svc = Service()
    handlers = {"ingest": cmd_ingest, "search": cmd_search, "generate": cmd_generate, "verify": cmd_verify, "complete": cmd_complete,
                "dedupe": cmd_dedupe, "eval": cmd_eval, "eval-retrieval": cmd_eval_retrieval, "serve": cmd_serve}
    try:
        handlers[a.cmd](svc, a)
    except (LLMError, RuntimeError, KeyError) as err:
        print(f"erro: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
