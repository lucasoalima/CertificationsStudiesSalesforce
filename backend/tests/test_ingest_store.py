import numpy as np

from qgen.ingest import chunk_text
from qgen.store import VectorStore


def test_chunks_are_tagged_by_cert_and_bounded(chunks):
    assert {c.cert for c in chunks} == {"d360", "sva"}
    assert all(len(c.text) <= 1100 for c in chunks)
    assert all(c.heading for c in chunks)


def test_long_section_is_windowed_with_overlap():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    cs = chunk_text("# Title\n\n" + body, "doc.md", None, max_chars=500, overlap=100)
    assert len(cs) > 3
    assert len({c.id for c in cs}) == len(cs)


def test_hashing_embedder_is_normalised_and_semantic_ish(embedder):
    v = embedder.embed(["identity resolution match rules", "match rules for identity resolution", "dashboard running user"])
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-5)
    assert v[0] @ v[1] > v[0] @ v[2]


def test_store_roundtrip_and_cert_filter(chunks, embedder, tmp_path):
    store = VectorStore.build(chunks, embedder)
    store.save(tmp_path)
    loaded = VectorStore.load(tmp_path)
    assert len(loaded.chunks) == len(chunks)
    res = loaded.search(embedder.embed(["sharing rules role hierarchy"])[0], k=4, cert="sva")
    assert len(res) == 4 and all(r.chunk.cert == "sva" for r in res)
    assert len({r.chunk.id for r in res}) == 4


def test_retrieval_finds_the_right_section(retriever):
    top = retriever.retrieve("family members share an address and get merged", k=1, cert="d360")[0]
    assert top.chunk.heading.endswith("Avoiding over-matching")
