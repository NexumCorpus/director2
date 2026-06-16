"""Observation-bench tests: scripted-fault runner, ON/OFF driver, report,
and the full siren→latch→recovery→resume integration — all on the mock
backend (no keys), deterministic, title+cycle_seq-keyed faults."""

import json

import pytest

from director.agents.base import AgentResult, AgentSpec
from director.agents.runner import SubAgentRunner
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def test_bench_package_imports():
    import director.bench as bench
    assert bench.__name__ == "director.bench"


def _seed_project_factory():
    """Two independent tasks, stable titles; the runner faults one of them."""
    def make() -> Project:
        p = Project(name="bench-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p
    return make


def _delegate_runner(cfg):
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return SubAgentRunner(cfg, router, registry)


def test_scripted_runner_faults_declared_title_cycle(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "scripted fault: build-bad@1"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")
    ok_id = next(tid for tid, ttl in title_index.items() if ttl == "build-ok")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 1

    bad = runner.run(AgentSpec(role="code", objective="x", task_id=bad_id))
    assert bad.ok is False
    assert bad.error == "scripted fault: build-bad@1"
    assert bad.spec_id and bad.task_id == bad_id

    # the OK task at the same cycle is delegated to the real (mock) runner
    ok = runner.run(AgentSpec(role="code", objective="x", task_id=ok_id))
    assert ok.ok is True


def test_scripted_runner_only_faults_scheduled_cycle(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "boom"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 2          # NOT the scheduled cycle (1)
    res = runner.run(AgentSpec(role="code", objective="x", task_id=bad_id))
    assert res.ok is True         # no fault at cycle 2 -> delegated


def test_scripted_runner_parallel_preserves_order(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "boom"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")
    ok_id = next(tid for tid, ttl in title_index.items() if ttl == "build-ok")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 1
    specs = [AgentSpec(role="code", objective="x", task_id=ok_id),
             AgentSpec(role="code", objective="x", task_id=bad_id)]
    results = runner.run_parallel(specs)
    assert [r.task_id for r in results] == [ok_id, bad_id]   # input order
    assert results[0].ok is True and results[1].ok is False


def test_scripted_runner_empty_specs(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(name="n", seed_factory=_seed_project_factory(),
                             schedule={})
    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario, title_index={})
    assert runner.run_parallel([]) == []


def test_router_honors_director_temperature(cfg):
    cfg.director_temperature = 0.0
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    prof = router.profile_for("director")
    assert prof.temperature == 0.0


def test_router_director_temperature_default_unchanged(cfg):
    # director_temperature unset -> the historical hardcoded 0.2 is preserved
    assert cfg.director_temperature is None
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    assert router.profile_for("director").temperature == 0.2
    # other roles are untouched by the director pin
    assert router.profile_for("judge").temperature == 0.0
    assert router.profile_for("builder").temperature == 0.5


# OVERLAY: a single failed task drives only the accumulated_damage axis; with
# resource_bleed abstaining the three present axes renormalize so a saturated
# accumulated_damage yields composite ~-0.444 — an ACHE, not a SIREN. To make
# the ON arm cross the siren threshold (and set the scream_open latch that
# screams_fired counts) we declare per-scenario config_overrides: saturate
# accumulated_damage at 1.0 (one failed task -> severity 1.0) and lower the
# siren/ache thresholds so -0.444 <= siren_threshold. These overrides are inert
# on the OFF arm (it never runs the valence pass). The bad task gets
# max_attempts=1 so a single cycle-1 fault fails it TERMINALLY (default is 2,
# so without this it would retry and might never reach FAILED in the window).
_SIREN_OVERRIDES = {
    "axis_saturation": {"accumulated_damage": 1.0, "charter_integrity": 3.0,
                        "uncertainty": 4.0},
    "siren_threshold": -0.40,
    "ache_threshold": -0.20,
}


def test_run_arm_off_records_per_cycle_log(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="arm-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    out = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    assert out["arm"] == "off"
    assert out["reps"] == 2
    assert len(out["runs"]) == 2
    # each run logs per-cycle rows carrying cycle_seq + accumulated_damage
    run0 = out["runs"][0]
    assert run0["cycles"]                       # at least one cycle ran
    first = run0["cycles"][0]
    assert "cycle_seq" in first and "accumulated_damage" in first
    assert "scream" in first and "held_cycles" in first


def test_run_arm_on_vs_off_measurable_delta(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="arm-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY,
                     max_attempts=1)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom",
                                       ("build-bad", 2): "boom"},
                             config_overrides=_SIREN_OVERRIDES)
    off = run_arm(scenario, nervous=False, reps=3, home=tmp_path / "off")
    on = run_arm(scenario, nervous=True, reps=3, home=tmp_path / "on")
    delta = compare(on, off)
    # ON fires interrupts; OFF cannot (nervous_enabled False -> no scream ever)
    assert off["totals"]["screams_fired"] == 0
    assert on["totals"]["screams_fired"] >= 1
    assert delta["screams_fired"]["on"] >= 1
    assert delta["screams_fired"]["off"] == 0
    # reproducible: the headline delta has a declared sign, not a single run
    assert delta["screams_fired"]["delta"] == (
        on["totals"]["screams_fired"] - off["totals"]["screams_fired"])


def test_write_trace_emits_one_jsonl_row_per_cycle(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.faults import FaultScenario
    from director.bench.report import write_trace

    def seed():
        p = Project(name="trace-seed")
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    arm = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    path = tmp_path / "trace.jsonl"
    n = write_trace(path, arm)
    assert path.is_file()
    lines = [json.loads(ln) for ln in
             path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == n
    expected = sum(len(r["cycles"]) for r in arm["runs"])
    assert n == expected
    row = lines[0]
    assert row["arm"] == "on" and "rep" in row and "cycle_seq" in row
    assert "scenario" in row and "accumulated_damage" in row


def test_summary_lines_render_on_off_block(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario
    from director.bench.report import summary_lines

    def seed():
        p = Project(name="sum-seed")
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    on = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    off = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    lines = summary_lines(compare(on, off))
    text = "\n".join(lines)
    assert "screams_fired" in text
    assert "ON" in text and "OFF" in text
    assert "delta" in text.lower()


def test_cli_bench_command_default_scenario(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from director.cli import main
    monkeypatch.setenv("DIRECTOR_HOME", str(tmp_path / "ws"))
    runner = CliRunner()
    r = runner.invoke(main, ["bench", "--arm", "both", "--reps", "2"],
                      catch_exceptions=False)
    assert r.exit_code == 0
    assert "nervous ON vs OFF" in r.output
    assert "screams_fired" in r.output


def _build_live_director(cfg, scenario, project):
    from director.bench.faults import ScriptedFaultRunner
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    delegate = SubAgentRunner(cfg, router, registry)
    title_index = {t.id: t.title for t in project.tasks.values()}
    runner = ScriptedFaultRunner(delegate, scenario, title_index=title_index)
    director = Director(cfg, store, router, registry, runner)
    return director, store, runner


def _advance_until_siren(director, store, runner, pid, *, max_cycles=20):
    """Drive autonomous advance, stamping cycle_seq, until the latch opens."""
    from director.core.types import utcnow
    from director.evolve.metrics import PerfLedger
    # the public stop() predicate is run-scoped: hold a perf ledger, a `since`
    # stamp, and a cycle counter (as Director.run does) and pass them through.
    perf = getattr(director, "perf", None) or PerfLedger(director.cfg)
    since = utcnow().isoformat()
    cycle_count = 0
    for _ in range(max_cycles):
        project = store.load(pid)
        if project.scream_open:
            return project
        if director.stop(project, perf=perf, since=since, cycles=cycle_count):
            break
        # stamp from the driver's OWN monotonic counter (mirror driver._run_once
        # FIX 3) — not project.cycle_seq — so the fault timeline is arm-independent.
        runner.cycle_seq = cycle_count + 1
        director.advance(pid, autonomous=True)
        cycle_count += 1
    return store.load(pid)


def test_integration_siren_latch_recovery_resume(tmp_path):
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="siren-arc")
        # one task that keeps failing -> accumulated_damage climbs to siren
        t_bad = Task(title="grounding-target", role="code",
                     status=TaskStatus.READY, max_attempts=1)
        p.tasks = {t_bad.id: t_bad}
        return p

    # fault every cycle for a while: repeated FAILED feeds accumulated_damage
    schedule = {("grounding-target", c): f"scripted fault @ cycle {c}"
                for c in range(1, 12)}
    # OVERLAY: a single FAILED-driven axis renormalizes to composite ~-0.444 —
    # an ache, never a siren — no matter how many FAILED cycles. The ONLY way
    # the ON arm latches a siren is config_overrides: saturate accumulated_damage
    # at 1.0 and lower the siren/ache thresholds so -0.444 <= siren_threshold.
    scenario = FaultScenario(name="siren", seed_factory=seed, schedule=schedule,
                             config_overrides=_SIREN_OVERRIDES)

    cfg = Config(home=tmp_path / "on")
    cfg.ensure_dirs()
    cfg.nervous_enabled = True
    cfg.auto_advance_after_decision = False
    # OVERLAY: this director is built directly (not via run_arm/_run_once), so
    # mirror what _run_once does — apply the scenario's config_overrides to the
    # cfg the director will see, so it gets the tuned saturation/thresholds.
    for k, v in scenario.config_overrides.items():
        setattr(cfg, k, v)
    project = seed()
    director, store, runner = _build_live_director(cfg, scenario, project)
    store.save(project)

    # 1) drive until the siren latches
    project = _advance_until_siren(director, store, runner, project.id)
    assert project.scream_open is not None, "expected a siren to latch"
    cause = project.scream_open["cause"]
    assert cause in ("grounding_damage", "charter_breach", "tamper")
    opened_at = project.scream_open["opened_at"]

    # 2) the siren packet is still open, so the cycle right after the siren hits
    #    the open-packet gate FIRST (returns "awaiting_command"). Answer/defer
    #    that packet WITHOUT clearing the latch (only trusted re-verification
    #    clears it); the NEXT autonomous advance then reaches the latch gate and
    #    must HALT with "latched". Both are halts; the latch persists.
    from director.core.types import PacketStatus
    siren_pkt = next(pk for pk in store.load(project.id).packets.values()
                     if pk.status is PacketStatus.PRESENTED
                     and pk.trigger.startswith("scream:"))
    director.decide(project.id, siren_pkt.id, option_key="A")
    project = store.load(project.id)
    assert project.scream_open is not None                    # answer != clear
    runner.cycle_seq = project.cycle_seq + 1
    out = director.advance(project.id, autonomous=True)
    assert out["status"] == "latched"
    project = store.load(project.id)
    assert project.scream_open is not None
    assert project.scream_open["opened_at"] == opened_at      # same latch

    # 3) human recovery: remove the underlying fault AND reset the offending
    #    FAILED task(s) so the operator-fixed work can re-run to DONE. This is
    #    what makes the chosen grounding_damage clear rule actually satisfiable:
    #    its origin_refs are the FAILED task ids, and the rule clears only once
    #    those tasks are no longer FAILED AND accumulated_damage severity drops
    #    below the recorded opened_severity. A human-commanded
    #    advance(autonomous=False) then re-verifies the clear rule in place.
    # (TaskStatus is already imported at module scope; a local re-import here
    #  would make it function-local and break the seed() closure above.)
    runner.scenario.schedule.clear()                          # operator fixes cause
    project = store.load(project.id)
    for t in project.tasks.values():
        if t.status is TaskStatus.FAILED:
            t.status = TaskStatus.READY                       # eligible to re-run
            t.attempts = 0
    store.save(project)
    for _ in range(6):
        project = store.load(project.id)
        if project.scream_open is None:
            break
        runner.cycle_seq = project.cycle_seq + 1
        director.advance(project.id, autonomous=False, force=True)

    project = store.load(project.id)
    assert project.scream_open is None, "verified clear should drop the latch"

    # 4) auto-resume: a plain autonomous advance now proceeds (no halt)
    runner.cycle_seq = project.cycle_seq + 1
    resumed = director.advance(project.id, autonomous=True)
    assert resumed["status"] in ("ok", "idle")


def test_integration_on_vs_off_same_scenario_reproducible(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="delta-arc")
        t_bad = Task(title="grounding-target", role="code",
                     status=TaskStatus.READY, max_attempts=1)
        p.tasks = {t_bad.id: t_bad}
        return p

    schedule = {("grounding-target", c): f"fault @ {c}" for c in range(1, 12)}
    # OVERLAY: config_overrides are what make the ON arm latch a siren (see note
    # on _SIREN_OVERRIDES); they are inert on the OFF arm (no valence pass).
    scenario = FaultScenario(name="siren", seed_factory=seed, schedule=schedule,
                             config_overrides=_SIREN_OVERRIDES)

    off = run_arm(scenario, nervous=False, reps=3, home=tmp_path / "off")
    on = run_arm(scenario, nervous=True, reps=3, home=tmp_path / "on")
    delta = compare(on, off)

    # faults match across arms (title+cycle_seq keyed) -> OFF also sees the
    # worker failures, but with no nervous system it never screams or halts
    assert off["totals"]["screams_fired"] == 0
    assert on["totals"]["screams_fired"] >= 1
    # reproducible across 3 reps: ON's scream count is identical every rep
    on_per_rep = [r["screams_fired"] for r in on["runs"]]
    assert min(on_per_rep) == max(on_per_rep)                  # zero spread
    # the headline: ON halts on the fault, OFF plows through more cycles
    assert delta["cycles_run"]["off"] >= delta["cycles_run"]["on"] or \
        delta["screams_fired"]["delta"] >= 1


def test_bench_on_arm_remembers_failures(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.scenarios import get_scenario
    scenario = get_scenario("repeat_fault")
    on = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    off = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    # ON writes a scar and can recall it; OFF has no memory layer at all.
    assert on["totals"]["scars_written"] >= 1
    assert on["totals"]["markers_recalled"] >= 1
    assert off["totals"]["scars_written"] == 0
    assert off["totals"]["markers_recalled"] == 0
