"""Gut Markers bias: a scarred signature is DEFERRED behind unscarred ready work,
without mutating the canonical deterministic frontier; OFF-path is byte-identical."""

import pytest

from director.agents.base import AgentResult, AgentSpec
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.taskgraph import ready_tasks
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.memory.markers import Marker, MarkerStore, task_signature
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.max_tasks_per_advance = 1          # only ONE dispatch per cycle -> repel must choose
    return c


class _OkRunner:
    def run_parallel(self, specs):
        return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role, ok=True,
                            output={"summary": "ok"}) for s in specs]


def _boss(cfg, markers):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return Director(cfg, store, router, registry, _OkRunner(), markers=markers)


def _two_ready(cfg):
    p = Project(name="gm")
    # distinct objectives so the two signatures do NOT spuriously collide under
    # the fuzzy recall threshold (marker_recall_sim=0.6): "implement the payment
    # retry ledger" vs "render the analytics dashboard charts" embed at cosine
    # ~0.23, so only the scarred task recalls its own scar. (The earlier
    # "the painful/fresh one" pair shared the "the ___ one" scaffold -> cosine
    # 0.617 > 0.6, which made the CLEAN task also read as scarred.)
    scarred = Task(title="Scarred", role="code", module_id="m1",
                   objective="implement the payment retry ledger",
                   status=TaskStatus.READY)
    clean = Task(title="Clean", role="code", module_id="m1",
                 objective="render the analytics dashboard charts",
                 status=TaskStatus.READY)
    p.tasks = {scarred.id: scarred, clean.id: clean}
    return p, scarred, clean


def test_scarred_signature_is_deferred_behind_clean_work(cfg):
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    # the scarred task's signature carries prior pain
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="hurt before",
                          last_cycle=0))
    boss = _boss(cfg, markers)
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)      # dispatches ONE; repel should pick CLEAN
    p2 = boss.store.load(p.id)
    assert p2.tasks[clean.id].status is TaskStatus.DONE       # clean ran first
    assert p2.tasks[scarred.id].status is TaskStatus.READY    # scarred deferred
    assert p2.marker_deferrals.get(scarred.id, 0) == 1


def test_canonical_ready_tasks_order_is_unchanged(cfg):
    # the bias is advisory; the canonical deterministic sort is NOT mutated.
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="d", last_cycle=0))
    before = [t.id for t in ready_tasks(p)]
    _boss(cfg, markers)        # constructing the director must not reorder the frontier
    after = [t.id for t in ready_tasks(p)]
    assert before == after


def test_off_path_no_repel(cfg):
    cfg.nervous_enabled = False
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="d", last_cycle=0))
    boss = _boss(cfg, markers)
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    # OFF: canonical order dispatches; no deferral tracking
    assert boss.store.load(p.id).marker_deferrals == {}
