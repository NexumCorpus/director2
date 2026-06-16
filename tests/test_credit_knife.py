"""Credit Knife: a RESOLVED failure (terminal FAILED) writes a problems-not-rubrics
scar; an in-flight retry writes nothing. Trusted-only, behind nervous_enabled."""

import pytest

import director.core.director as dmod
from director.agents.base import AgentResult, AgentSpec
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.memory.markers import MarkerStore, task_signature
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


class _FailRunner:
    """Every dispatched spec fails with a content error (non-transient)."""
    def run_parallel(self, specs):
        return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role,
                            ok=False, error="add() returned a-b not a+b")
                for s in specs]


def _boss(cfg, runner):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return Director(cfg, store, router, registry, runner,
                    markers=MarkerStore(cfg))


def test_terminal_failure_writes_a_scar(cfg):
    boss = _boss(cfg, _FailRunner())
    p = Project(name="ck")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY,
             max_attempts=1)            # fails terminally on the first attempt
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    scars = boss.markers.recall(task_signature(t))
    assert len(scars) == 1
    sc = scars[0]
    assert sc.cause == "failed_verification"
    assert "add()" in sc.diagnosis            # carries the failing case
    # problems-not-rubrics: no numeric valence/threshold/weight leaked into the text
    for forbidden in ("-0.", "valence", "threshold", "weight"):
        assert forbidden not in sc.diagnosis.lower()
    assert sc.origin                          # non-empty (synthetic origin for a plan task)


def test_transient_retry_writes_no_scar(cfg):
    class _TransientRunner:
        def run_parallel(self, specs):
            return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role,
                                ok=False, error="rate limit exceeded (429)")
                    for s in specs]
    boss = _boss(cfg, _TransientRunner())
    p = Project(name="ck2")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY, max_attempts=2)
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)      # transient -> READY retry, NOT terminal
    assert boss.markers.recall(task_signature(t)) == []


def test_off_path_writes_no_scar(cfg):
    cfg.nervous_enabled = False
    boss = _boss(cfg, _FailRunner())
    p = Project(name="ck3")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY, max_attempts=1)
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    assert boss.markers.recall(task_signature(t)) == []   # markers untouched OFF
