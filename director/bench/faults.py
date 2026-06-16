"""Scripted fault injection for the observation bench.

``ScriptedFaultRunner`` duck-types the ``SubAgentRunner`` seam (run / run_parallel
-> AgentResult) used by the Director (director.py:748). For a declared
(task_title, cycle_seq) pair it returns AgentResult(ok=False, error=...) so a
worker "fails" deterministically; every other spec is delegated to a real
injected runner so the Director's OWN planning/packet calls still hit the real
router (the subject stays pinned). Schedules key on task TITLE + cycle_seq, not
ids — ids are uuid4 (types.py:25) and never match across arms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..agents.base import AgentResult, AgentSpec
from ..core.types import Project


@dataclass
class FaultScenario:
    """A reproducible bench scenario: how to build the starting project and
    when workers fail. ``schedule`` maps (task_title, cycle_seq) -> error str.

    ``config_overrides`` are declared per-scenario Config tweaks the driver
    applies to the ON arm AFTER the standard bench setup (saturation points /
    thresholds are first-guesses the spec says are tuned via this bench). They
    are inert on the OFF arm, which never runs the valence pass."""
    name: str
    seed_factory: Callable[[], Project]
    schedule: dict[tuple[str, int], str] = field(default_factory=dict)
    config_overrides: dict = field(default_factory=dict)


class ScriptedFaultRunner:
    """A drop-in ``SubAgentRunner`` replacement that injects declared faults.

    The Director holds it as ``self.runner`` and calls ``run_parallel(specs)``
    each cycle. The harness stamps the current ``cycle_seq`` on this runner
    (``runner.cycle_seq = project.cycle_seq``) BEFORE each advance so faults
    fire on the right cycle. Specs carry only ``task_id``; ``title_index`` maps
    ``task_id -> title`` so the schedule can key on the stable title.
    """

    def __init__(self, delegate, scenario: FaultScenario, *,
                 title_index: dict[str, str]):
        self.delegate = delegate
        self.scenario = scenario
        self.title_index = dict(title_index)
        self.cycle_seq = 0
        self.injected: list[dict] = []     # observability: faults actually fired

    # --------------------------------------------------------------- single
    def run(self, spec: AgentSpec) -> AgentResult:
        title = self.title_index.get(spec.task_id, "")
        err = self.scenario.schedule.get((title, self.cycle_seq))
        if err is not None:
            self.injected.append({"title": title, "cycle_seq": self.cycle_seq,
                                  "error": err})
            return AgentResult(spec_id=spec.id, task_id=spec.task_id,
                               role=spec.role, ok=False, error=err)
        return self.delegate.run(spec)

    # --------------------------------------------------------------- parallel
    def run_parallel(self, specs: list[AgentSpec]) -> list[AgentResult]:
        # results return in input order (mirror SubAgentRunner.run_parallel);
        # run() never raises, so a simple ordered map is correct and keeps the
        # per-cycle fault log deterministic across arms.
        return [self.run(s) for s in specs]
