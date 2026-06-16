"""Bench driver: run one arm (nervous ON or OFF) over a scripted scenario for
N reps, logging the dependent variables per cycle_seq, then compare arms.

The driver owns the cycle accounting the ScriptedFaultRunner needs: it stamps
``runner.cycle_seq`` before each ``advance(autonomous=True)`` so faults fire on
the declared cycle. This re-implements run()'s bounded loop locally (run() does
the same minus the stamp); the loop owns NO state authority — every write still
routes through advance()/store.save (Constitution f).
"""

from __future__ import annotations

from pathlib import Path

from ..agents.runner import SubAgentRunner
from ..config import Config
from ..core.director import Director
from ..core.state import ProjectStore
from ..core.types import utcnow
from ..evolve.metrics import PerfLedger
from ..llm.mock import MockBackend
from ..llm.router import LLMRouter
from ..verify import make_default_registry
from .faults import FaultScenario, ScriptedFaultRunner


def _build_director(cfg: Config, scenario: FaultScenario, project):
    """Mirror server.py:79-95 wiring, but wrap the runner in a fault runner."""
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    delegate = SubAgentRunner(cfg, router, registry)
    title_index = {t.id: t.title for t in project.tasks.values()}
    runner = ScriptedFaultRunner(delegate, scenario, title_index=title_index)
    director = Director(cfg, store, router, registry, runner)
    return director, store, runner


def _run_once(scenario: FaultScenario, *, nervous: bool, home: Path,
              max_cycles: int = 12) -> dict:
    cfg = Config(home=home)
    cfg.ensure_dirs()
    cfg.nervous_enabled = nervous
    cfg.auto_advance_after_decision = False     # mirror server.py:71
    # OVERLAY: declared per-scenario Config tweaks (saturation/thresholds). Inert
    # on the OFF arm (it never runs the valence pass), so they only shape the ON
    # arm — legitimate declared bench setup (thresholds are spec first-guesses
    # tuned via this bench). Applied AFTER nervous/auto-advance so they win.
    for k, v in scenario.config_overrides.items():
        setattr(cfg, k, v)
    project = scenario.seed_factory()
    director, store, runner = _build_director(cfg, scenario, project)
    store.save(project)

    # the stop() predicate is run-scoped: hold a perf ledger, a `since` stamp,
    # and a cycle counter just as Director.run() does, and pass them in.
    perf = getattr(director, "perf", None) or PerfLedger(cfg)
    since = utcnow().isoformat()
    cycle_count = 0
    cycles: list[dict] = []
    for _ in range(max_cycles):
        project = store.load(project.id)
        if director.stop(project, perf=perf, since=since, cycles=cycle_count):
            break
        # faults key on the cycle the worker will run in: advance() increments
        # cycle_seq before the valence pass, so the worker batch in THIS advance
        # runs at cycle_seq+1 — stamp the runner to match.
        runner.cycle_seq = project.cycle_seq + 1
        result = director.advance(project.id, autonomous=True)
        cycle_count += 1
        project = store.load(project.id)
        body = project.body
        scream = project.scream_open
        cycles.append({
            "cycle_seq": project.cycle_seq,
            "status": result.get("status"),
            "done": result.get("done", 0),
            "failed": result.get("failed", 0),
            "new_packets": len(result.get("new_packets", [])),
            "accumulated_damage": (getattr(body, "accumulated_damage", 0.0)
                                   if body is not None else 0.0),
            "valence": (getattr(body, "valence", 0.0)
                        if body is not None else 0.0),
            "scream": (scream.get("cause") if scream else None),
            "held_cycles": (scream.get("held_cycles", 0) if scream else 0),
        })
        if result.get("status") in ("latched", "awaiting_command"):
            break       # a packet OR a held latch halted the autonomous loop

    screams = [c for c in cycles if c["scream"]]
    return {
        "nervous": nervous,
        "cycles": cycles,
        "injected": list(runner.injected),
        "screams_fired": len(screams),
        "diagnostic_tasks": sum(c["new_packets"] for c in cycles),
        "final_damage": cycles[-1]["accumulated_damage"] if cycles else 0.0,
        "cycles_run": len(cycles),
        "outcome": cycles[-1]["status"] if cycles else "drained",
    }


def run_arm(scenario: FaultScenario, *, nervous: bool, reps: int,
            home: Path) -> dict:
    """Run one arm for N reps; return per-run logs + aggregate totals."""
    arm = "on" if nervous else "off"
    runs = []
    for i in range(reps):
        runs.append(_run_once(scenario, nervous=nervous,
                              home=Path(home) / f"rep{i}"))
    totals = {
        "screams_fired": sum(r["screams_fired"] for r in runs),
        "diagnostic_tasks": sum(r["diagnostic_tasks"] for r in runs),
        "cycles_run": sum(r["cycles_run"] for r in runs),
        "final_damage": sum(r["final_damage"] for r in runs),
    }
    return {"arm": arm, "scenario": scenario.name, "reps": reps,
            "runs": runs, "totals": totals}


def _spread(runs: list[dict], key: str) -> dict:
    vals = [r[key] for r in runs]
    n = len(vals) or 1
    return {"mean": round(sum(vals) / n, 3),
            "min": min(vals) if vals else 0,
            "max": max(vals) if vals else 0}


def compare(on_results: dict, off_results: dict) -> dict:
    """ON-vs-OFF comparison summary with per-arm spread (never a single run)."""
    metrics = ("screams_fired", "diagnostic_tasks", "cycles_run", "final_damage")
    out: dict = {}
    for m in metrics:
        on_v = on_results["totals"][m]
        off_v = off_results["totals"][m]
        out[m] = {"on": on_v, "off": off_v, "delta": on_v - off_v,
                  "on_spread": _spread(on_results["runs"], m),
                  "off_spread": _spread(off_results["runs"], m)}
    return out
