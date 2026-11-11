import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qgen.config import Settings, load_outlines  # noqa: E402
from qgen.embeddings import HashingEmbedder  # noqa: E402
from qgen.ingest import load_corpus  # noqa: E402
from qgen.llm import FakeLLM  # noqa: E402
from qgen.store import Retriever, VectorStore  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "data" / "docs"


@pytest.fixture(scope="session")
def outlines():
    return load_outlines()


@pytest.fixture(scope="session")
def embedder():
    return HashingEmbedder()


@pytest.fixture(scope="session")
def chunks(outlines):
    return load_corpus(DOCS, set(outlines))


@pytest.fixture()
def retriever(chunks, embedder):
    return Retriever(VectorStore.build(chunks, embedder), embedder)


def _ids(prompt):
    return re.findall(r"^\[([0-9a-f]{12})\]", prompt, flags=re.M)


GOOD = [
    {"q": "Northern Trail Outfitters must keep family members as separate profiles even though they share an address. What should the consultant do?",
     "o": ["Match only on address", "Combine a contact point with an individual attribute in the match rule", "Disable identity resolution", "Use one match rule on phone"],
     "a": 1, "e": "Regras mais restritivas evitam over-matching."},
    {"q": "Cumulus Financial needs to match customers on a loyalty number. Which object holds the identifier for an exact match rule?",
     "o": ["Contact Point Email", "Sales Order", "Party Identification", "Unified Link Individual"],
     "a": "C", "e": "Party Identification guarda identificadores customizados."},
    {"q": "bad", "o": ["same", "same", "x"], "a": 0},  # invalid: duplicate options
    {"q": "No key here", "o": ["a", "b", "c", "d"]},  # invalid: missing key
]


def make_fake(solver_agrees=True, supported=True, payload=None):
    def respond(prompt: str) -> str:
        ids = _ids(prompt)
        if "Write" in prompt and "ORIGINAL multiple-choice" in prompt:
            items = [dict(x, sources=ids) for x in (payload or GOOD)]
            return "```json\n" + json.dumps(items) + "\n```"
        if "Answer this certification question" in prompt:
            if "loyalty number" in prompt:
                ans = "C" if solver_agrees else "A"
            else:
                ans = "B" if solver_agrees else "D"
            return json.dumps({"answer": [ans], "supported": supported, "support_ids": ids, "ambiguous": False, "issues": []})
        if "You review practice questions" in prompt:
            n = prompt.count("### Q")
            return json.dumps([{"a": ["B"], "e": "ok", "s": "ir", "confidence": "high"}] * n)
        return "{}"
    return FakeLLM(respond)


@pytest.fixture()
def settings(tmp_path):
    s = Settings()
    s.index_dir = tmp_path / "index"
    s.reports_dir = tmp_path / "reports"
    s.out_dir = tmp_path / "out"
    return s
