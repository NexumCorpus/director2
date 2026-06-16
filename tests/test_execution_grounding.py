"""Execution grounding for the command loop: code/test deliverables are RUN, not
just judged. python_parses (pure) + code_runs + tests_pass (isolated subprocess),
auto-declared for code/test tasks, with the safety screen as containment."""

import json

from director.verify.execution import exec_safety_violations, run_module, run_pytest
from director.verify.properties import partial_bundle_ok, run_properties

GOOD = ("from __future__ import annotations\n"
        "import time\n__all__=['TokenBucket']\n"
        "class TokenBucket:\n"
        "    def __init__(self, rate, capacity):\n"
        "        if rate<=0: raise ValueError('rate')\n"
        "        self.rate=rate; self.capacity=capacity; self.tokens=capacity\n"
        "    def consume(self, n=1):\n"
        "        if self.tokens>=n:\n            self.tokens-=n; return True\n"
        "        return False\n")


# ---- safety screen: broad-but-safe ----------------------------------------
def test_exec_screen_allows_real_code_blocks_danger():
    assert exec_safety_violations(GOOD) == []          # __future__/__all__/time ok
    assert exec_safety_violations("import dataclasses\n@dataclasses.dataclass\n"
                                  "class C:\n    x: int = 0\n") == []
    assert exec_safety_violations("import os\nos.system('x')")          # blocked
    assert exec_safety_violations("eval('1+1')")                        # blocked
    assert exec_safety_violations("import subprocess")                  # blocked
    assert exec_safety_violations("x = ().__class__.__bases__")         # escape dunder


def test_run_module():
    assert run_module(GOOD)[0] is True
    assert run_module("raise RuntimeError('boom')")[0] is False
    assert run_module("import os\nos.system('echo hi')")[0] is False   # screened


def test_threading_is_allowed():
    # live-arc finding: a token bucket legitimately uses threading.Lock — a safe
    # stdlib import must not false-fail code_runs (it has no IO/net/escape).
    threaded = ("import threading\n"
                "class Bucket:\n"
                "    def __init__(self):\n"
                "        self._lock = threading.Lock()\n"
                "        self.tokens = 5\n"
                "    def consume(self):\n"
                "        with self._lock:\n"
                "            if self.tokens > 0:\n"
                "                self.tokens -= 1; return True\n"
                "            return False\n"
                "Bucket().consume()\n")
    assert exec_safety_violations(threaded) == []
    assert run_module(threaded)[0] is True


# ---- the code checkers earn a partial (force-to-fail proven) ---------------
def test_python_parses_and_code_runs_count():
    rep = run_properties(GOOD, ["python_parses", "code_runs"])
    assert rep["n_passed"] == 2 and rep["force_to_fail_ok"]
    assert partial_bundle_ok(rep)
    # a syntactically broken deliverable earns nothing
    bad = run_properties("def (:\n  oops", ["python_parses"])
    assert bad["n_passed"] == 0


def test_tests_pass_counts_against_reference_code():
    tests = ("import impl\n"
             "def test_consume():\n"
             "    assert impl.TokenBucket(1.0,5).consume(1) is True\n"
             "def test_empty():\n"
             "    tb=impl.TokenBucket(1.0,1)\n"
             "    assert tb.consume(1) and not tb.consume(1)\n")
    rep = run_properties(tests, ["tests_pass"], ref=GOOD, ref_independent=True)
    assert rep["n_passed"] == 1 and partial_bundle_ok(rep)
    # tests that contradict the code do NOT pass
    wrong = ("import impl\n"
             "def test_wrong():\n"
             "    assert impl.TokenBucket(1.0,5).consume(1) is False\n")
    assert run_properties(wrong, ["tests_pass"], ref=GOOD,
                          ref_independent=True)["n_passed"] == 0


def test_tests_pass_rejects_vacuous_tests():
    # RED-TEAM FIX: a test that asserts NOTHING about the impl must not earn a
    # tests_pass badge. Force-to-fail mutates the REFERENCE (neutralized impl) and
    # requires the test to catch it — only a behavioral test does. (Before the
    # fix, force-to-fail mutated the test file, so `assert True` earned a badge.)
    code = "class Calc:\n    def add(self, a, b):\n        return a + b\n"
    behavioral = ("import impl\n"
                  "def test_add():\n    assert impl.Calc().add(2, 3) == 5\n")
    vacuous = "def test_true():\n    assert True\n"
    import_only = ("import impl\n"
                   "def test_smoke():\n    impl.Calc()\n    assert True\n")
    assert run_properties(behavioral, ["tests_pass"], ref=code,
                          ref_independent=True)["n_passed"] == 1
    assert run_properties(vacuous, ["tests_pass"], ref=code,
                          ref_independent=True)["n_passed"] == 0       # forgery dead
    assert run_properties(import_only, ["tests_pass"], ref=code,
                          ref_independent=True)["n_passed"] == 0


# ---- auto-declaration for code/test tasks ----------------------------------
def test_plan_autodeclares_execution_grounding(cfg):
    from director.core.director import (CharterOut, Director, ModuleOut, PlanOut,
                                        TaskOut)
    from director.core.state import ProjectStore
    from director.core.types import Project
    from director.agents.runner import SubAgentRunner
    from director.llm.mock import MockBackend
    from director.llm.router import LLMRouter
    from director.verify import make_default_registry
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    reg = make_default_registry()
    boss = Director(cfg, store, router, reg, SubAgentRunner(cfg, router, reg))
    plan = PlanOut(
        charter=CharterOut(objective="ship code"),
        modules=[ModuleOut(name="build")],
        tasks=[TaskOut(title="Implement the limiter", role="research",
                       objective="reference implementation", module="build"),
               TaskOut(title="Write the adversarial test suite", role="research",
                       objective="pytest cases", module="build")])
    p = Project(name="x")
    boss._ingest_plan(p, "ship code", plan)
    by = {t.title: t for t in p.tasks.values()}
    impl = by["Implement the limiter"]
    tst = by["Write the adversarial test suite"]
    assert impl.role == "code" and "python_parses" in impl.properties \
        and "code_runs" in impl.properties
    assert tst.role == "test" and "tests_pass" in tst.properties


def _boss(cfg):
    from director.core.director import Director
    from director.core.state import ProjectStore
    from director.agents.runner import SubAgentRunner
    from director.llm.mock import MockBackend
    from director.llm.router import LLMRouter
    from director.verify import make_default_registry
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    reg = make_default_registry()
    return Director(cfg, store, router, reg, SubAgentRunner(cfg, router, reg))


def test_run_module_requires_substance():
    assert run_module("import time\n'just a docstring'\n")[0] is False
    assert run_module("# only a comment\npass\n")[0] is False
    assert run_module("def f():\n    return 1\nf()\n")[0] is True


def test_grounding_failure_recorded_as_risk(cfg):
    from director.core.types import AgentRun, Project, Task
    boss = _boss(cfg)
    p = Project(name="broken")
    t = Task(title="implement", role="code", properties=["code_runs"])
    p.tasks[t.id] = t
    run = AgentRun(task_id=t.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, t, run.id, {"artifacts": [
        {"title": "bad.py", "kind": "code", "content": "def (:\n  broken"}]})
    deliv = [a for a in p.artifacts.values() if a.title == "bad.py"][0]
    assert "partial" not in deliv.provenance               # broken code: no badge
    assert any("code_runs" in (r.title or "") for r in p.risks.values())


def test_finalize_includes_verification_ledger(cfg):
    from director.core.types import Artifact, ArtifactStatus, Project
    boss = _boss(cfg)
    p = boss.store.create("ledger")
    code = Artifact(title="m.py", kind="code", content="x = 1",
                    status=ArtifactStatus.CURRENT,
                    provenance={"partial": {"n_passed": 1, "n_total": 1,
                                            "checks": ["code_runs"],
                                            "report_id": "r"}})
    spec = Artifact(title="spec.md", kind="markdown", content="prose",
                    status=ArtifactStatus.CURRENT)
    p.artifacts[code.id], p.artifacts[spec.id] = code, spec
    boss.store.save(p)
    boss.finalize(p.id)
    final = [a for a in boss.store.load(p.id).artifacts.values()
             if a.title.startswith("FINAL")][0]
    assert "Verification ledger" in final.content
    assert "code_runs" in final.content and "judged" in final.content


def test_code_task_deliverable_earns_partial_through_ingest(cfg):
    from director.core.types import AgentRun, Project, Task
    boss = _boss(cfg)
    p = Project(name="grounded")
    t = Task(title="implement", role="code",
             properties=["python_parses", "code_runs"])
    p.tasks[t.id] = t
    run = AgentRun(task_id=t.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, t, run.id, {"artifacts": [
        {"title": "token_bucket.py", "kind": "code", "content": GOOD}]})
    deliv = [a for a in p.artifacts.values() if a.title == "token_bucket.py"][0]
    part = deliv.provenance.get("partial", {})
    assert part.get("n_passed") == 2
    assert set(part.get("checks", [])) == {"python_parses", "code_runs"}
