from conftest import make_fake

from qgen.bank import load_bank, save_app_json
from qgen.dedupe import dedupe
from qgen.pipeline import complete_keys, generate
from qgen.schemas import Question


def run(outlines, retriever, embedder, **kw):
    fake = kw.pop("fake", None) or make_fake()
    return generate(outline=outlines["d360"], section_key="ir", n=4, retriever=retriever, writer=fake, solver=fake, embedder=embedder, **kw), fake


def test_generate_validates_verifies_and_cites(outlines, retriever, embedder):
    res, fake = run(outlines, retriever, embedder, keep="all")
    assert res.stats.raw == 4 and res.stats.schema_valid == 2
    assert len(res.stats.invalid_reasons) == 2
    assert res.stats.citations_valid == 2
    assert all(q.s == "ir" and q.cert == "d360" for q in res.questions)
    assert res.questions[1].a == 2  # letter "C" normalised to index
    assert res.stats.accepted == 2 and all(v.agrees for v in res.verdicts.values())


def test_disagreeing_unsupported_questions_are_rejected(outlines, retriever, embedder):
    res, _ = run(outlines, retriever, embedder, fake=make_fake(solver_agrees=False, supported=False), keep="accepted")
    assert res.questions == []
    assert res.stats.rejected + res.stats.review == 2


def test_dedupe_against_existing_bank(outlines, retriever, embedder):
    first, _ = run(outlines, retriever, embedder, keep="all")
    second, _ = run(outlines, retriever, embedder, keep="all", existing=first.questions)
    assert second.stats.duplicates == 2 and second.questions == []


def test_semantic_dedupe_catches_paraphrase(embedder):
    a = Question(id="a", q="Which object stores a loyalty ID for exact matching in identity resolution?", o=["Party Identification", "Sales Order", "Individual"], a=0)
    b = Question(id="b", q="Which object stores the loyalty ID used for exact matching in identity resolution?", o=["Sales Order", "Party Identification", "Individual"], a=1)
    c = Question(id="c", q="What does a dynamic dashboard show?", o=["x", "y", "z"], a=0)
    res = dedupe([b, c], [a], embedder, threshold=0.8)
    assert [q.id for q in res.kept] == ["c"] and res.dropped[0][1] == "a"


def test_bank_roundtrip_and_complete(outlines, retriever, tmp_path):
    p = tmp_path / "bank.json"
    p.write_text('[{"q":"Q1?","o":["a","b","c","d"],"a":"B"},{"q":"Q2 without key?","o":["a","b","c","d"]},{"q":"","o":[]}]')
    qs, errs = load_bank(p, "d360")
    assert len(qs) == 2 and qs[0].a == 1 and qs[1].a is None and errs
    done = complete_keys(outline=outlines["d360"], items=[qs[1]], retriever=retriever, llm=make_fake())
    assert done[0][0].a == 1 and done[0][0].s == "ir"
    save_app_json([qs[0], done[0][0]], tmp_path / "out.json")
    again, _ = load_bank(tmp_path / "out.json")
    assert [q.a for q in again] == [1, 1]
