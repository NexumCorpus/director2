"""Hardening from the live Sonnet arc: role inference, heavy-agent timeouts,
deliverable selection for property checks, dead-backend quarantine."""

import json

from director.config import LONG_CALL_KINDS, Config
from director.core.director import _infer_role
from director.errors import ModelError, ModelProviderError, ModelTransientError
from director.llm.base import LLMBackend, LLMResponse
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter

KNOWN = {"research", "code", "test", "review", "simulation", "synthesis"}


# ---- 1. role inference (planner labeled everything "research") -------------
def test_infer_role_recovers_specialists():
    assert _infer_role("Write Adversarial Test Suite", "pytest cases",
                       "research", KNOWN) == "test"
    assert _infer_role("Implement Token-Bucket Rate Limiter",
                       "reference implementation", "research", KNOWN) == "code"
    assert _infer_role("Define Limiter Config JSON Schema", "draft-07",
                       "research", KNOWN) == "code"
    assert _infer_role("Execute Tests and Simulation", "run the sim",
                       "research", KNOWN) == "simulation"
    assert _infer_role("Final Review and Integration Report", "audit",
                       "research", KNOWN) == "review"
    # an EXPLICIT specialist role is trusted, never downgraded
    assert _infer_role("anything", "", "code", KNOWN) == "code"
    # genuinely research-y work stays research
    assert _infer_role("Survey prior rate-limiter designs", "gather evidence",
                       "research", KNOWN) == "research"


# ---- 2. heavy task subagents get the long timeout lane --------------------
def test_agent_kinds_get_long_timeout():
    c = Config(request_timeout_s=120.0)
    assert c.kind_timeout("agent_research") == 360.0      # 3x — was timing out
    assert c.kind_timeout("agent_code") == 360.0
    assert c.kind_timeout("agent_synthesis") == 360.0
    assert c.kind_timeout("initial_plan") == 360.0        # still long
    assert c.kind_timeout("command_packet") == 120.0      # packets stay fast
    assert c.kind_timeout("ping") == 120.0


# ---- 3. property check verifies the substantive artifact, not a doc -------
def _boss(cfg):
    from director.agents.runner import SubAgentRunner
    from director.core.director import Director
    from director.core.state import ProjectStore
    from director.llm.router import LLMRouter as R
    from director.verify import make_default_registry
    store = ProjectStore(cfg)
    router = R(cfg, backends={"mock": MockBackend()})
    reg = make_default_registry()
    return Director(cfg, store, router, reg, SubAgentRunner(cfg, router, reg))


def test_partial_verifies_json_not_markdown_sidecar(cfg):
    from director.core.types import AgentRun, Artifact, Project, Task, TaskStatus
    SCHEMA = {"type": "object", "required": ["w"],
              "properties": {"w": {"type": "integer", "minimum": 1,
                                   "maximum": 9}}}
    boss = _boss(cfg)
    p = Project(name="sidecar")
    schema_task = Task(title="define schema", role="code",
                       status=TaskStatus.DONE)
    sa = Artifact(title="s.schema.json", kind="code",
                  content=json.dumps(SCHEMA), task_id=schema_task.id)
    schema_task.artifact_ids = [sa.id]
    p.artifacts[sa.id] = sa
    p.tasks[schema_task.id] = schema_task
    ex = Task(title="produce example", role="code",
              depends_on=[schema_task.id], properties=["schema_valid"])
    p.tasks[ex.id] = ex
    run = AgentRun(task_id=ex.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    # the task emits the VALID json AND an (invalid) annotated markdown sidecar
    boss._ingest_output(p, ex, run.id, {"artifacts": [
        {"title": "example.json", "kind": "json", "content": json.dumps({"w": 5})},
        {"title": "example_annotated.md", "kind": "markdown",
         "content": "{\"_comment\":\"docs\",\"w\":5}  not schema-valid"}]})
    deliv = [a for a in p.artifacts.values() if a.title == "example.json"][0]
    sidecar = [a for a in p.artifacts.values()
               if a.title == "example_annotated.md"][0]
    assert deliv.provenance.get("partial", {}).get("n_passed") == 1  # the JSON
    assert "partial" not in sidecar.provenance                       # not the doc


# ---- 4. quarantine a dead (402) backend; don't hammer it ------------------
class _Boom(LLMBackend):
    default_model = "x"

    def __init__(self, nm, exc):
        self.name, self._exc, self.calls = nm, exc, 0

    def complete(self, system, user, *, model, temperature, max_tokens,
                 timeout_s, kind=""):
        self.calls += 1
        raise self._exc


class _Ok(LLMBackend):
    default_model = "ok"

    def __init__(self, nm="good"):
        self.name, self.calls = nm, 0

    def complete(self, system, user, *, model, temperature, max_tokens,
                 timeout_s, kind=""):
        self.calls += 1
        return LLMResponse(text="ok", backend=self.name)


def test_dead_backend_quarantined_after_402(cfg):
    dead = _Boom("openrouter", ModelProviderError("HTTP 402: Insufficient credits"))
    good = _Ok("claude_cli")
    # primary=dead, good failover (insertion order sets primary)
    r = LLMRouter(cfg, backends={"openrouter": dead, "claude_cli": good})
    assert r.complete("s", "u", kind="agent_code").backend == "claude_cli"
    assert r.complete("s", "u", kind="agent_code").backend == "claude_cli"
    assert dead.calls == 1        # tried once, then quarantined (not hammered)
    assert good.calls == 2
    assert "openrouter" in r._dead


def test_transient_failure_does_not_quarantine(cfg):
    flaky = _Boom("openrouter", ModelTransientError("timed out"))
    good = _Ok("claude_cli")
    r = LLMRouter(cfg, backends={"openrouter": flaky, "claude_cli": good})
    r.complete("s", "u", kind="agent_code")
    r.complete("s", "u", kind="agent_code")
    assert flaky.calls == 2       # transient: retried, NOT quarantined
    assert "openrouter" not in r._dead


def test_transient_401_not_quarantined_despite_message(cfg):
    """The live-arc bug: claude_cli's subscription 401 is a recoverable blip, so
    it surfaces as ModelTransientError. Quarantine keys off the exception TYPE,
    not the string — a transient error that merely MENTIONS 401 must keep its
    backend live, or one auth hiccup kills the only backend for the whole run."""
    flaky = _Boom("claude_cli", ModelTransientError(
        "claude CLI auth failed after 3 attempts (transient 401 - ...)"))
    r = LLMRouter(cfg, backends={"claude_cli": flaky})
    assert LLMRouter._is_dead_error(flaky._exc) is False   # type, not substring
    # sole backend: a transient 401 keeps it live so a later call can recover,
    # rather than being permanently quarantined on the first blip
    for _ in range(3):
        try:
            r.complete("s", "u", kind="agent_code")
        except Exception:                              # noqa: BLE001
            pass
    assert "claude_cli" not in r._dead
    assert flaky.calls == 3        # retried every call, never quarantined


# ---- 5. status surfaces a failed task that's blocking dependents ----------
def test_status_surfaces_blocked_failed_task(cfg):
    from director.core.types import Project, Task, TaskStatus
    boss = _boss(cfg)
    p = boss.store.create("cascade")
    bad = Task(title="write tests", role="test", status=TaskStatus.FAILED,
               error="timed out")
    dep = Task(title="run tests", role="simulation", depends_on=[bad.id],
               status=TaskStatus.PENDING)
    p.tasks[bad.id], p.tasks[dep.id] = bad, dep
    boss.store.save(p)
    st = boss.status(p.id)
    assert bad.id in st["failed_ids"]
    assert st["next_action"].startswith("retry")     # not a silent "advance"


# ---- 6. run-scoped perf view -----------------------------------------------
def test_perf_stats_since(cfg):
    from director.evolve.metrics import PerfLedger
    pl = PerfLedger(cfg)
    pl.record({"ts": "2020-01-01T00:00:00", "ok": True, "backend": "old"})
    pl.record({"ts": "2026-06-14T00:00:00", "ok": True, "backend": "new"})
    pl.record({"ts": "2026-06-14T00:01:00", "ok": False, "backend": "new"})
    assert pl.stats()["calls"] == 3                       # cumulative
    scoped = pl.stats(since="2026-06-14T00:00:00")
    assert scoped["calls"] == 2 and scoped["by_backend"] == {"new": 2}


# ---- 7. charter deliverables backfilled when the planner omits them --------
def test_charter_deliverables_backfilled(cfg):
    from director.core.director import (CharterOut, ModuleOut, PlanOut, TaskOut)
    from director.core.types import Project
    boss = _boss(cfg)
    plan = PlanOut(
        charter=CharterOut(objective="ship a thing", deliverables=[]),
        modules=[ModuleOut(name="build")],
        tasks=[TaskOut(title="Implement the thing", role="research",
                       module="build"),
               TaskOut(title="Write the spec", role="research", module="build")])
    p = Project(name="x")
    boss._ingest_plan(p, "ship a thing", plan)
    assert p.charter.deliverables                          # no longer empty
    assert "Implement the thing" in p.charter.deliverables


# ---- 8. a packet always gets a recommendation ------------------------------
def test_ensure_recommendation():
    from director.core.director import _ensure_recommendation
    from director.core.types import CommandOption, CommandPacket
    pk = CommandPacket(title="t", options=[
        CommandOption(key="a", label="A", conviction="dogmatic"),
        CommandOption(key="b", label="B", conviction="iconoclast")])
    assert pk.recommendation_key == ""
    _ensure_recommendation(pk)
    assert pk.recommendation_key == "a"                   # defaulted to first
    pk.recommendation_key = "b"
    _ensure_recommendation(pk)
    assert pk.recommendation_key == "b"                   # a valid one is kept


# ---- 9. finalize is honest about incomplete/failed work --------------------
def test_finalize_reports_gaps(cfg):
    from director.core.types import (Artifact, ArtifactStatus, Task, TaskStatus)
    boss = _boss(cfg)
    p = boss.store.create("gappy")
    done = Task(title="spec", role="research", status=TaskStatus.DONE)
    a = Artifact(title="spec.md", kind="markdown", content="the spec",
                 task_id=done.id, status=ArtifactStatus.CURRENT)
    done.artifact_ids = [a.id]
    bad = Task(title="adversarial test suite", role="test",
               status=TaskStatus.FAILED, error="claude CLI timed out")
    p.tasks[done.id], p.tasks[bad.id], p.artifacts[a.id] = done, bad, a
    boss.store.save(p)
    boss.finalize(p.id)
    final = [x for x in boss.store.load(p.id).artifacts.values()
             if x.title.startswith("FINAL")][0]
    assert "Known gaps" in final.content
    assert "adversarial test suite" in final.content      # the failed task named


# ---- 10. transient vs content failure classification -----------------------
def test_is_transient_failure():
    from director.core.director import _is_transient_failure
    assert _is_transient_failure("claude CLI timed out after 360s")
    assert _is_transient_failure("ModelTransientError: rate limit")
    assert _is_transient_failure("HTTP 429 Too Many Requests")
    assert not _is_transient_failure("schema validation failed: missing 'w'")
    assert not _is_transient_failure("HTTP 402 Insufficient credits")
