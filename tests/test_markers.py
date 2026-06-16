"""Gut Markers store: signature recall + merge-and-strengthen (the explicit fix
for the lesson ledger's silent _DEDUPE_SIM drop). Offline, deterministic, no model."""

import pytest

from director.config import Config
from director.core.types import Task
from director.memory.markers import Marker, MarkerStore, task_signature


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    return c


def test_task_signature_is_role_module_objective():
    t = Task(title="Build add()", role="code", module_id="m1",
             objective="Implement add(a, b)")
    assert task_signature(t) == "code|m1|implement add(a, b)"
    # falls back to the title when objective is empty
    t2 = Task(title="Build It", role="code", module_id="m1")
    assert task_signature(t2) == "code|m1|build it"


def test_record_inserts_then_recall_returns_it(cfg):
    store = MarkerStore(cfg)
    m = store.record(Marker(signature="code|m1|implement add",
                            cause="failed_verification",
                            diagnosis="add() returned a-b not a+b", last_cycle=1))
    assert m.weight == pytest.approx(-cfg.marker_repel_step)
    assert m.count == 1
    hits = store.recall("code|m1|implement add")
    assert len(hits) == 1
    assert hits[0].diagnosis == "add() returned a-b not a+b"
    assert hits[0].weight < 0


def test_record_merges_and_strengthens_on_repeat(cfg):
    # a recurring scar DEEPENS (more negative weight, count++) — NOT a silent drop.
    store = MarkerStore(cfg)
    store.record(Marker(signature="code|m1|implement add",
                        cause="failed_verification", diagnosis="first", last_cycle=1))
    m2 = store.record(Marker(signature="code|m1|implement add",
                             cause="grounding_damage", diagnosis="again", last_cycle=2))
    assert m2.count == 2
    assert m2.weight == pytest.approx(-2 * cfg.marker_repel_step)
    assert m2.diagnosis == "again"          # diagnosis refreshed to the latest
    # only ONE marker exists for that signature (merged, not duplicated)
    assert len(store.recall("code|m1|implement add")) == 1


def test_weight_clamped_at_floor(cfg):
    store = MarkerStore(cfg)
    for i in range(50):
        store.record(Marker(signature="code|m1|x", cause="failed_verification",
                            diagnosis="d", last_cycle=i))
    assert store.recall("code|m1|x")[0].weight >= cfg.marker_repel_floor


def test_recall_excludes_below_similarity(cfg):
    store = MarkerStore(cfg)
    store.record(Marker(signature="code|m1|implement add",
                        cause="failed_verification", diagnosis="d", last_cycle=1))
    # an unrelated signature recalls nothing above the recall threshold
    assert store.recall("research|m9|write a market analysis report") == []


def test_persists_across_instances(cfg):
    MarkerStore(cfg).record(Marker(signature="code|m1|implement add",
                                   cause="failed_verification", diagnosis="d",
                                   last_cycle=1))
    assert len(MarkerStore(cfg).recall("code|m1|implement add")) == 1
