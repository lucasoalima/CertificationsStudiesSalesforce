from conftest import make_fake
from fastapi.testclient import TestClient

from qgen import api
from qgen.evaluate import eval_generation, eval_retrieval, load_retrieval_set, write_report
from qgen.service import Service
from conftest import DOCS


class FakeService(Service):
    def __init__(self, settings, retriever, embedder):
        super().__init__(settings)
        self._retriever, self._embedder = retriever, embedder

    def llm(self, spec=None):
        return make_fake()


def test_api_generate_and_verify(settings, retriever, embedder, monkeypatch):
    svc = FakeService(settings, retriever, embedder)
    monkeypatch.setattr(api, "get_service", lambda: svc)
    c = TestClient(api.app)
    assert c.get("/health").json()["chunks"] == len(retriever.store.chunks)
    r = c.post("/generate", json={"cert": "d360", "section": "ir", "n": 4})
    assert r.status_code == 200
    body = r.json()
    assert len(body["questions"]) == 2 and body["stats"]["schema_valid"] == 2
    assert set(body["questions"][0]) >= {"q", "o", "a", "e", "s", "t"}
    v = c.post("/verify", json={"cert": "d360", "questions": body["questions"]}).json()
    assert len(v["verdicts"]) == 2
    assert c.post("/generate", json={"cert": "nope", "section": "ir"}).status_code == 404


def test_eval_generation_and_report(outlines, retriever, embedder, chunks, tmp_path):
    fake = make_fake()
    m, qs = eval_generation(outline=outlines["d360"], sections=["ir"], n_per_section=4, retriever=retriever, writer=fake, judge=fake, embedder=embedder)
    s = m.summary()
    assert s["schema_valid_rate"] == 0.5 and s["agreement_rate"] == 1.0 and s["acceptance_rate"] == 1.0
    items = load_retrieval_set(DOCS.parent / "eval" / "retrieval.jsonl")
    rr = eval_retrieval(chunks, embedder, items)
    assert rr["n"] == 30 and 0 <= rr["mrr"] <= 1
    path = write_report(tmp_path, "teste", [rr], [s])
    text = path.read_text(encoding="utf-8")
    assert "Recall" in text or "recall@1" in text
    assert "agreement_rate" in text
