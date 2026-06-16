"""Bench reporting: a JSONL trace (one row per cycle, mirroring PerfLedger's
append-a-JSON-line idiom, metrics.py:29) plus a human-readable ON/OFF summary.
The trace is the durable evidence base; the summary is the readout."""

from __future__ import annotations

import json
from pathlib import Path


def write_trace(path, arm_result: dict) -> int:
    """Write one JSON line per (rep, cycle) for an arm. Returns rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with path.open("a", encoding="utf-8") as fh:
        for rep_i, run in enumerate(arm_result["runs"]):
            for cyc in run["cycles"]:
                row = {"arm": arm_result["arm"],
                       "scenario": arm_result["scenario"],
                       "rep": rep_i, **cyc}
                fh.write(json.dumps(row) + "\n")
                rows += 1
    return rows


def summary_lines(comparison: dict) -> list[str]:
    """Render the ON/OFF comparison (from driver.compare) as text lines."""
    lines = ["== BENCH: nervous ON vs OFF =="]
    header = f"{'metric':<18} {'ON':>8} {'OFF':>8} {'delta':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for metric, vals in comparison.items():
        lines.append(f"{metric:<18} {vals['on']:>8} {vals['off']:>8} "
                     f"{vals['delta']:>8}")
        lines.append(f"  spread ON {vals['on_spread']}  "
                     f"OFF {vals['off_spread']}")
    return lines
