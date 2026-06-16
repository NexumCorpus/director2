"""Calibration — a conviction's TRACK RECORD against genuine oracle outcomes.

This is the honest answer to "conviction steering is UX, not verification": it
makes the steering layer *self-measuring*. For each command-packet pick, it asks
whether the work that pick SPAWNED later cleared a trusted check, and reports a
per-conviction rate.

Three honesty rules, all load-bearing:

1. **Not a verification tier.** Calibration NEVER elevates an option's check or
   touches :func:`honest_check`. "This commander's iconoclast picks clear trusted
   checks 60% of the time" is a fact about the *picker's track record* — a
   different thing from "this deliverable is verified." Keeping them separate is
   what stops calibration from laundering faith into apparent ground truth.

2. **Un-forgeable evidence only.** A pick is "vindicated" only when a task it
   spawned earned ``provenance['partial']`` — engine-stamped by trusted code,
   which agents cannot write. An agent-declared ``kind == "verification"``
   artifact is NOT trusted here (agents control artifact kind), so a model cannot
   manufacture its own good track record.

3. **Recorded link, honest abstention.** Attribution uses the RECORDED
   ``task.origin_decision_id`` (stamped when the decision created the task), never
   inferred causality. Decisions whose spawned tasks are still in flight are not
   scored; a rate is reported only once enough decisions have RESOLVED.
"""

from __future__ import annotations

from .convictions import CONVICTIONS, _PICK_RESPONSES, _option_by_key
from .types import Project, Task, TaskStatus

#: a conviction needs at least this many RESOLVED decisions before any rate is
#: reported — below it, calibration honestly says "insufficient history".
MIN_SAMPLE = 3

_TERMINAL = {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}


def _task_vindicated(project: Project, task: Task) -> bool:
    """A task cleared a GENUINE, un-forgeable trusted outcome. Anchored solely on
    ``provenance['partial']`` (stamped by trusted code in _run_task_properties);
    an agent-set artifact ``kind`` is deliberately NOT trusted here."""
    for aid in task.artifact_ids:
        art = project.artifacts.get(aid)
        if art and (getattr(art, "provenance", None) or {}).get("partial"):
            return True
    return False


def _decision_conviction(project: Project, dec) -> str | None:
    pkt = project.packets.get(dec.packet_id)
    if not pkt:
        return None
    opt = _option_by_key(pkt, dec.selected_key)
    return opt.conviction if opt else None


def calibration_record(project: Project) -> dict:
    """Per-conviction track record:
    ``{conviction: {decisions, resolved, vindicated, rate|None, label}}``.

    * ``decisions`` — picks of that conviction that SPAWNED at least one task.
    * ``resolved`` — of those, picks whose every spawned task is terminal.
    * ``vindicated`` — resolved picks with >=1 spawned task that cleared a
      trusted check.
    * ``rate`` — ``vindicated/resolved``, or ``None`` until ``resolved >=
      MIN_SAMPLE`` (honest abstention).
    """
    spawned: dict[str, list[Task]] = {}
    for t in project.tasks.values():
        if t.origin_decision_id:
            spawned.setdefault(t.origin_decision_id, []).append(t)

    rec = {c.value: {"decisions": 0, "resolved": 0, "vindicated": 0,
                     "rate": None, "label": ""} for c in CONVICTIONS}
    for dec in project.decisions.values():
        if dec.response_type not in _PICK_RESPONSES:
            continue
        conv = _decision_conviction(project, dec)
        if conv not in rec:
            continue
        tasks = spawned.get(dec.id, [])
        if not tasks:
            continue                      # the pick created no tasks to judge
        rec[conv]["decisions"] += 1
        if all(t.status in _TERMINAL for t in tasks):
            rec[conv]["resolved"] += 1
            if any(_task_vindicated(project, t) for t in tasks):
                rec[conv]["vindicated"] += 1

    for r in rec.values():
        if r["resolved"] >= MIN_SAMPLE:
            r["rate"] = round(r["vindicated"] / r["resolved"], 2)
            r["label"] = (f"{r['vindicated']}/{r['resolved']} resolved picks "
                          f"cleared a trusted check")
        else:
            r["label"] = f"insufficient oracle history (n={r['resolved']})"
    return rec


def calibration_read(project: Project) -> str:
    """One-line honest read — names a stance's track record only where it has
    enough RESOLVED history; otherwise states that ground truth is still scarce."""
    rec = calibration_record(project)
    scored = {c: r for c, r in rec.items() if r["rate"] is not None}
    if not scored:
        return ("Calibration: not enough verified outcomes yet — a track record "
                "forms only as picks clear trusted checks.")
    parts = [f"{c} {r['rate']:.0%} ({r['vindicated']}/{r['resolved']})"
             for c, r in scored.items()]
    return "Calibration — " + "; ".join(parts)
