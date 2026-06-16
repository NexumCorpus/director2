"""Memory tests: embedding determinism, retrieval relevance, persistence,
lesson dedupe + digest."""

from director.memory.lessons import LessonLedger
from director.memory.store import MemoryStore
from director.memory.vector import VectorStore, cosine, embed


def test_embed_deterministic_and_normalized():
    a = embed("fallout dialogue tree quest design")
    b = embed("fallout dialogue tree quest design")
    assert a == b
    norm = sum(v * v for v in a)
    assert abs(norm - 1.0) < 1e-9


def test_similarity_orders_related_above_unrelated():
    q = embed("sensor coverage mesh simulation for ISR drones")
    related = embed("ISR drone sensor mesh coverage modeling")
    unrelated = embed("banana bread recipe with extra cinnamon")
    assert cosine(q, related) > cosine(q, unrelated) + 0.2


def test_vector_store_roundtrip(tmp_path):
    vs = VectorStore(tmp_path / "idx.json")
    vs.add("a", "cache eviction policy with ghost entries")
    vs.add("b", "reactive dialogue tree for wasteland NPCs")
    hits = vs.search("NPC dialogue trees", k=1)
    assert hits[0]["id"] == "b"
    # reload from disk
    vs2 = VectorStore(tmp_path / "idx.json")
    assert len(vs2) == 2
    assert vs2.search("eviction ghost cache", k=1)[0]["id"] == "a"
    assert vs2.remove("a") and len(vs2) == 1


def test_memory_store_remember_recall_forget(cfg):
    ms = MemoryStore(cfg)
    nid = ms.remember("Director 2.0 uses event-sourced project state",
                      kind="fact", tags=["architecture"])
    other = ms.remember("RimWorld modpack uses 63 active mods", kind="fact")
    hits = ms.recall("event sourced state architecture")
    assert hits and hits[0]["id"] == nid
    assert ms.get(other)["text"].startswith("RimWorld")
    assert ms.forget(nid)
    assert ms.get(nid) is None
    assert all(h["id"] != nid for h in ms.recall("event sourced state"))


def test_lessons_dedupe_and_digest(cfg):
    ledger = LessonLedger(cfg)
    l1 = ledger.add("always bound the context injected into prompts",
                    tags=["prompting"], source="run1")
    assert l1 is not None
    dup = ledger.add("always bound the context injected into prompts")
    assert dup is None                      # near-duplicate rejected
    l2 = ledger.add("sandbox every generated snippet before trusting it",
                    tags=["safety"], source="run2")
    assert l2 is not None
    assert len(ledger) == 2
    d = ledger.digest("untrusted generated code sandboxing")
    assert "sandbox every generated snippet" in d
    # bounded
    cfg.lessons_digest_max = 1
    assert len(ledger.digest().splitlines()) == 1
    # persisted across instances
    ledger2 = LessonLedger(cfg)
    assert len(ledger2) == 2 and len(ledger2.all()) == 2
