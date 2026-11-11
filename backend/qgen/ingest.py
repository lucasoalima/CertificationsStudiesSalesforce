"""Load documents (Markdown, text, HTML, PDF) and split them into retrievable chunks.

Chunking is heading-aware: text is first split by Markdown headings (or blank-line
paragraphs for other formats), then packed into windows of ~`max_chars` characters
with `overlap` characters carried over, so a chunk rarely cuts a sentence in half.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .schemas import Chunk

SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf"}


def read_document(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in {".html", ".htm"}:
        from bs4 import BeautifulSoup  # optional dependency

        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        lines = []
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "pre"]):
            txt = el.get_text(" ", strip=True)
            if not txt:
                continue
            if el.name in {"h1", "h2", "h3", "h4"}:
                lines.append("#" * int(el.name[1]) + " " + txt)
            else:
                lines.append(txt)
        return "\n\n".join(lines)
    if ext == ".pdf":
        from pypdf import PdfReader  # optional dependency

        reader = PdfReader(str(path))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    raise ValueError(f"unsupported file type: {path}")


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _sections(text: str) -> list[tuple[str, str]]:
    """Split text into (heading, body) pairs using Markdown headings."""
    out: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []  # (level, title) path of the current heading
    buf: list[str] = []

    def heading() -> str:
        return " > ".join(t for _, t in stack)

    for line in text.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            if "".join(buf).strip():
                out.append((heading(), "\n".join(buf).strip()))
            level = len(m.group(1))
            stack = [x for x in stack if x[0] < level] + [(level, m.group(2).strip())]
            buf = []
        else:
            buf.append(line)
    if "".join(buf).strip():
        out.append((heading(), "\n".join(buf).strip()))
    return out


def _windows(text: str, max_chars: int, overlap: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:  # break very long paragraphs on sentence boundaries
        if len(p) <= max_chars:
            pieces.append(p)
            continue
        sent = re.split(r"(?<=[.!?])\s+", p)
        cur = ""
        for s in sent:
            if cur and len(cur) + len(s) + 1 > max_chars:
                pieces.append(cur)
                cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            pieces.append(cur)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
            cur = f"{tail}\n\n{p}".strip() if tail else p
        else:
            cur = f"{cur}\n\n{p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def chunk_text(text: str, doc: str, cert: str | None, max_chars: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, body in _sections(text):
        for i, w in enumerate(_windows(body, max_chars, overlap)):
            cid = hashlib.sha1(f"{doc}|{heading}|{i}|{w[:80]}".encode()).hexdigest()[:12]
            chunks.append(Chunk(id=cid, doc=doc, heading=heading, text=w, cert=cert))
    return chunks


def load_corpus(docs_dir: Path, known_certs: set[str], max_chars: int = 900, overlap: int = 150) -> list[Chunk]:
    """Walk `docs_dir`; a sub-folder named after a cert id (e.g. d360/) tags its chunks with that cert."""
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        rel = path.relative_to(docs_dir)
        cert = next((p for p in rel.parts[:-1] if p in known_certs), None)
        text = read_document(path)
        chunks.extend(chunk_text(text, rel.as_posix(), cert, max_chars, overlap))
    return chunks
