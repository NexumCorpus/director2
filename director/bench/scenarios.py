"""Named bench scenarios. Each is a FaultScenario: a seed-project factory plus
a (task_title, cycle_seq)-keyed fault schedule. Titles are stable across arms;
ids (uuid4) are not, so the schedule keys on titles.
"""

from __future__ import annotations

from ..core.types import Project, Task, TaskStatus
from .faults import FaultScenario

# OVERLAY: a single FAILED-driven axis (accumulated_damage, others 0,
# resource_bleed abstaining) renormalizes to weight 0.40/0.90 ~= 0.444, so even
# a fully-saturated accumulated_damage yields composite ~-0.444 — an ACHE, never
# a SIREN (-0.66). The ONLY way the ON arm latches a siren is the per-scenario
# config_overrides mechanism (faults.py FaultScenario / driver._run_once): we
# saturate accumulated_damage at 1.0 (one FAILED task -> severity 1.0) and lower
# the siren/ache thresholds so -0.444 <= siren_threshold. These are inert on the
# OFF arm (it never runs the valence pass). Paired with a build-bad task of
# max_attempts=1 so one cycle-1 fault fails it TERMINALLY (default 2 would retry
# and might never reach FAILED in the window). Same set proven in Task 5.4.
_SIREN_OVERRIDES = {
    "axis_saturation": {"accumulated_damage": 1.0, "charter_integrity": 3.0,
                        "uncertainty": 4.0},
    "siren_threshold": -0.40,
    "ache_threshold": -0.20,
}


def _default_seed() -> Project:
    p = Project(name="bench-default")
    t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
    t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY,
                 max_attempts=1)
    p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
    return p


_SCENARIOS = {
    "default": lambda: FaultScenario(
        name="default",
        seed_factory=_default_seed,
        schedule={("build-bad", 1): "scripted fault: build-bad failed at cycle 1",
                  ("build-bad", 2): "scripted fault: build-bad failed at cycle 2"},
        config_overrides=_SIREN_OVERRIDES),
}


def scenario_names() -> list[str]:
    return sorted(_SCENARIOS)


def get_scenario(name: str) -> FaultScenario:
    if name not in _SCENARIOS:
        raise KeyError(f"unknown bench scenario '{name}'; "
                       f"have {scenario_names()}")
    return _SCENARIOS[name]()
