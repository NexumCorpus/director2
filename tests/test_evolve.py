"""Evolve layer tests: perf ledger, improvement loop (offline, real sandbox),
declared verdicts, prompt evolution with human command."""

import json

from director.evolve.domains import TopKDomain, domain_names, get_domain
from director.evolve.loop import ImprovementLoop
from director.evolve.metrics import PerfLedger
from director.evolve.prompts import PromptRegistry
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def make_router(cfg, scripts=None, recorder=None):
    return LLMRouter(cfg, backends={"mock": MockBackend(scripts=scripts)},
                     recorder=recorder)


# ---------------------------------------------------------------- perf ledger
def test_perf_ledger_records_and_aggregates(cfg):
    ledger = PerfLedger(cfg)
    router = make_router(cfg, recorder=ledger.recorder)
    router.complete("s", "u", kind="agent_research", role="director")
    router.complete("s", "u", kind="agent_research", role="director")
    stats = ledger.stats()
    assert stats["calls"] == 2 and stats["ok_rate"] == 1.0
    assert stats["by_kind"]["agent_research"]["calls"] == 2
    assert ledger.kind_ok_rate("agent_research")["ok_rate"] == 1.0
    assert ledger.failure_samples("agent_research") == []


# ------------------------------------------------------------------- the loop
def test_loop_matches_baseline_with_fixture(cfg):
    """Mock builder proposes sorted-slice == baseline -> verdict 'matches'."""
    cfg.loop_iterations = 2
    cfg.bench_repeats = 1
    loop = ImprovementLoop(cfg, make_router(cfg), TopKDomain())
    report = loop.run()
    assert report.candidates_correct >= 1
    assert report.verdict == "matches", report
    assert report.mean_margin is not None and abs(report.mean_margin) <= 0.01
    assert report.declared_rule
    # artifacts on disk
    from pathlib import Path
    run_dir = Path(report.run_dir)
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "best_solution.py").is_file()
    assert (run_dir / "report.txt").is_file()
    saved = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "matches"
    # adversary hardened the suite with the fixture workload
    assert any(w["name"] == "adversarial_duplicates"
               for w in report.hostile_workloads_added)


def test_loop_below_verdict_for_degraded_candidate(cfg):
    """A candidate correct on small criteria cases but weak on large
    workloads must be declared 'below' (overfit caught by measurement)."""
    cfg.loop_iterations = 1
    cfg.bench_repeats = 1
    degraded = json.dumps({
        "rationale": "fast path for big inputs",
        "algo_class": "shortcut",
        "code": ("def solve(items, k):\n"
                 "    if len(items) < 100:\n"
                 "        return sorted(items)[:k]\n"
                 "    return sorted(items[:max(1, len(items)//10)])[:k]\n")})
    router = make_router(cfg, scripts={"builder_propose": [degraded]})
    loop = ImprovementLoop(cfg, router, TopKDomain())
    report = loop.run()
    assert report.candidates_correct == 1
    assert report.verdict == "below", report
    assert report.mean_margin < -0.01
    assert report.margins_by_workload


def test_loop_handles_broken_proposals(cfg):
    """Incorrect proposals produce problems-only feedback and never crash."""
    cfg.loop_iterations = 2
    cfg.bench_repeats = 1
    bad = json.dumps({"rationale": "off by one", "algo_class": "buggy",
                      "code": "def solve(items, k):\n"
                              "    return sorted(items)[:k-1]\n"})
    good = json.dumps({"rationale": "fix", "algo_class": "sorted_slice",
                       "code": "def solve(items, k):\n"
                               "    return sorted(items)[:k]\n"})
    mb = MockBackend(scripts={"builder_propose": [bad, good]})
    router = LLMRouter(cfg, backends={"mock": mb})
    loop = ImprovementLoop(cfg, router, TopKDomain())
    report = loop.run()
    assert report.candidates_total == 2
    assert report.candidates_correct == 1
    assert report.verdict == "matches"
    # second builder call received causal feedback (expected vs got)
    second_call = [c for c in mb.calls if c["kind"] == "builder_propose"][1]
    assert "OBSERVED PROBLEMS" in second_call["user"]
    assert "expected" in second_call["user"]


def test_loop_lessons_recorded(cfg):
    from director.memory.lessons import LessonLedger
    cfg.loop_iterations = 1
    cfg.bench_repeats = 1
    lessons = LessonLedger(cfg)
    loop = ImprovementLoop(cfg, make_router(cfg), TopKDomain(), lessons=lessons)
    loop.run()
    assert len(lessons) == 1
    assert "discovery[topk]" in lessons.all()[0]["text"]


def test_domain_registry():
    assert "topk" in domain_names()
    assert get_domain("topk").name == "topk"


# ------------------------------------------------------------ prompt registry
def test_prompt_registry_lifecycle(cfg):
    reg = PromptRegistry(cfg)
    text = reg.ensure("role_code", "You are a coding agent. Strict JSON.")
    assert "coding agent" in text
    assert reg.info("role_code")["active"] == 1
    # override returns active for registered, default for unregistered
    assert reg.override("role_code", "x") == text
    assert reg.override("role_research", "default text") == "default text"

    router = make_router(cfg)
    proposal = reg.propose_mutation("role_code", router,
                                    failure_samples=["schema validation failed"])
    assert proposal["version"] == 2 and proposal["status"] == "proposed"
    # proposal is NOT active until human command
    assert reg.info("role_code")["active"] == 1
    assert "precise agent" not in reg.text("role_code")
    # human applies
    reg.apply("role_code", 2)
    assert reg.info("role_code")["active"] == 2
    assert reg.text("role_code") == "You are a precise agent. Return strict JSON only."
    assert reg.info("role_code")["versions"]["1"]["status"] == "retired"
    # reject path
    p2 = reg.propose_mutation("role_code", router)
    reg.reject("role_code", p2["version"])
    assert reg.info("role_code")["versions"][str(p2["version"])]["status"] == "rejected"
    # persisted across instances
    reg2 = PromptRegistry(cfg)
    assert reg2.info("role_code")["active"] == 2


def test_runner_uses_evolved_prompt(cfg):
    from director.agents.base import AgentSpec
    from director.agents.runner import SubAgentRunner
    reg = PromptRegistry(cfg)
    reg.ensure("role_research", "EVOLVED RESEARCH PROMPT v1. Return JSON.")
    mb = MockBackend()
    router = LLMRouter(cfg, backends={"mock": mb})
    runner = SubAgentRunner(cfg, router, make_default_registry(), prompts=reg)
    runner.run(AgentSpec(role="research", objective="o", task_id="t"))
    assert mb.calls[0]["system"].startswith("EVOLVED RESEARCH PROMPT v1")
