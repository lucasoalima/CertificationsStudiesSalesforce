"""Runtime settings, read from environment variables (or a .env file)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import ExamOutline

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    docs_dir: Path = field(default_factory=lambda: Path(os.getenv("QGEN_DOCS_DIR", ROOT / "data" / "docs")))
    index_dir: Path = field(default_factory=lambda: Path(os.getenv("QGEN_INDEX_DIR", ROOT / "data" / "index")))
    out_dir: Path = field(default_factory=lambda: Path(os.getenv("QGEN_OUT_DIR", ROOT / "data" / "out")))
    reports_dir: Path = field(default_factory=lambda: Path(os.getenv("QGEN_REPORTS_DIR", ROOT / "reports")))

    # LLM
    provider: str = field(default_factory=lambda: os.getenv("QGEN_PROVIDER", "anthropic"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    temperature: float = field(default_factory=lambda: float(os.getenv("QGEN_TEMPERATURE", "0.4")))

    # Embeddings
    embedder: str = field(default_factory=lambda: os.getenv("QGEN_EMBEDDER", "hashing"))
    ollama_embed_model: str = field(default_factory=lambda: os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    st_model: str = field(default_factory=lambda: os.getenv("ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))

    # Chunking / retrieval
    chunk_chars: int = field(default_factory=lambda: int(os.getenv("QGEN_CHUNK_CHARS", "900")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("QGEN_CHUNK_OVERLAP", "150")))
    top_k: int = field(default_factory=lambda: int(os.getenv("QGEN_TOP_K", "6")))

    # Quality gates
    min_grounding: float = field(default_factory=lambda: float(os.getenv("QGEN_MIN_GROUNDING", "0.6")))
    dup_threshold: float = field(default_factory=lambda: float(os.getenv("QGEN_DUP_THRESHOLD", "0.88")))


def get_settings() -> Settings:
    return Settings()


def load_outlines(path: Path | None = None) -> dict[str, ExamOutline]:
    path = path or ROOT / "data" / "exam_outlines.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {x["id"]: ExamOutline(**x) for x in raw}
