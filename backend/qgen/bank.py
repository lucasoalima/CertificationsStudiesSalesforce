"""Read and write question banks in the web app's JSON format (Importar / Exportar)."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .schemas import Question
from .verify import _parse_letters


def to_app(q: Question) -> dict:
    d = {"q": q.q, "o": q.o, "a": q.a, "e": q.e, "s": q.s, "t": q.t, "src": "ai" if q.src == "rag" else q.src}
    if q.meta.get("verdict") and q.meta["verdict"] != "accepted":
        d["n"] = "Questão marcada para revisão pelo verificador automático."
    return d


def save_app_json(questions: list[Question], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([to_app(q) for q in questions], ensure_ascii=False, indent=1), encoding="utf-8")


def load_bank(path: Path, cert: str = "") -> tuple[list[Question], list[str]]:
    """Load an app export / any JSON list of {q, o, a?, e?, s?, t?}. Returns (questions, errors)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("questions", [raw])
    out, errors = [], []
    for i, x in enumerate(raw):
        try:
            o = x.get("o") or x.get("options") or []
            if isinstance(o, dict):
                o = [o[k] for k in sorted(o)]
            a_raw = x.get("a", x.get("answer"))
            idx = _parse_letters(a_raw, len(o)) if a_raw is not None else []
            a = None if not idx else (idx if len(idx) > 1 else idx[0])
            q = Question(
                id=str(x.get("id") or f"{cert or 'q'}-{i}"), q=str(x.get("q") or x.get("question") or ""), o=[str(v) for v in o], a=a,
                e=str(x.get("e") or x.get("explanation") or ""), s=str(x.get("s") or ""), t=str(x.get("t") or ""),
                src=str(x.get("src") or "import"), cert=cert,
            )
            if not q.q:
                raise ValueError("empty question")
            out.append(q)
        except (ValidationError, ValueError, TypeError, AttributeError) as e:
            errors.append(f"#{i}: {str(e).splitlines()[0][:100]}")
    return out, errors
