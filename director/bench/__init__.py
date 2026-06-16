"""Director 2.0 observation bench.

Runs the autonomous loop nervous-ON vs nervous-OFF on the SAME scripted-fault
scenario so the behavioral delta of the functional-valence nervous system is
measured, never asserted. Failures are injected deterministically by a scripted
runner keyed on (task_title, cycle_seq) — titles are author-controlled and
stable across arms; entity ids are uuid4 and are NOT (types.py:25).

This package never grades the model. It observes the trusted loop.
"""

from __future__ import annotations

from .faults import FaultScenario, ScriptedFaultRunner
from .driver import compare, run_arm
from .report import summary_lines, write_trace

__all__ = ["FaultScenario", "ScriptedFaultRunner", "run_arm", "compare",
           "summary_lines", "write_trace"]
