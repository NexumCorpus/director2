"""Coherence pass — deterministic invariant checking before any state delta is
applied, plus the delta application itself (one module owns delta semantics).

A StateDelta's payload may carry:
    module_updates:  [{"module_id", "status"?, "note"?}]
    task_updates:    [{"task_id", "status"?, "note"?}]
    new_tasks:       [{"title", "role", "module_id"?, "objective"?, "depends_on"?: [task ids]}]
    risk_updates:    [{"risk_id"? , "title"?, "level"?, "status"?, "mitigation"?}]
    artifact_updates:[{"artifact_id", "status"}]
    assumption_updates: [{"assumption_id"?, "statement"?, "status"?}]
    notes:           ["..."]

Conflicts (unknown ids, illegal transitions, frozen-module edits, dependency
cycles) BLOCK the delta and require human judgment — the Director never forces
an incoherent mutation through.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import CoherenceBlockedError
from ..logging_setup import get_logger
from .taskgraph import detect_cycles
from .types import (Assumption, ModuleStatus, Project, Risk, RiskLevel,
                    RiskStatus, StateDelta, Task, TaskStatus, utcnow)

log = get_logger("coherence")

_LEGAL_MODULE = {
    ModuleStatus.PROPOSED: {ModuleStatus.ACTIVE, ModuleStatus.DEPRECATED},
    ModuleStatus.ACTIVE: {ModuleStatus.IN_COMMAND, ModuleStatus.FROZEN,
                          ModuleStatus.BLOCKED, ModuleStatus.COMPLETED,
                          ModuleStatus.DEPRECATED},
    ModuleStatus.IN_COMMAND: {ModuleStatus.ACTIVE, ModuleStatus.FROZEN,
                              ModuleStatus.COMPLETED},
    ModuleStatus.FROZEN: {ModuleStatus.ACTIVE},
    ModuleStatus.BLOCKED: {ModuleStatus.ACTIVE, ModuleStatus.DEPRECATED},
    ModuleStatus.COMPLETED: {ModuleStatus.ACTIVE},          # reopen (warned)
    ModuleStatus.DEPRECATED: set(),
}

_LEGAL_TASK = {
    # READY/PENDING -> BLOCKED is a deliberate human hold (freeze gate) —
    # live finding 2026-06-12: a ratified packet legitimately wanted to gate
    # scenario authoring until schemas landed. Nothing auto-resumes BLOCKED;
    # release requires another explicit delta (BLOCKED -> READY).
    TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.CANCELLED,
                         TaskStatus.BLOCKED},
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED,
                       TaskStatus.PENDING, TaskStatus.BLOCKED},
    TaskStatus.RUNNING: {TaskStatus.NEEDS_VERIFY, TaskStatus.DONE,
                         TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.NEEDS_VERIFY: {TaskStatus.DONE, TaskStatus.FAILED,
                              TaskStatus.READY, TaskStatus.BLOCKED},
    TaskStatus.FAILED: {TaskStatus.READY, TaskStatus.CANCELLED},
    # BLOCKED -> PENDING releases a hold back into the dependency pool
    # (refresh_statuses promotes it to READY only when deps are met)
    TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED,
                         TaskStatus.PENDING},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class CoherenceReport:
    status: str = "clear"                      # clear | warnings | blocked
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_human: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.conflicts)


def coherence_pass(project: Project, delta: StateDelta, *,
                   actor: str = "director") -> CoherenceReport:
    """Validate a proposed delta against project invariants. Read-only."""
    rep = CoherenceReport()
    payload = delta.payload or {}

    for upd in payload.get("module_updates", []):
        mid = str(upd.get("module_id", ""))
        module = project.modules.get(mid)
        if module is None:
            rep.conflicts.append(f"module_updates: unknown module '{mid}'")
            continue
        new_status = upd.get("status")
        if new_status:
            try:
                target = ModuleStatus(new_status)
            except ValueError:
                rep.conflicts.append(
                    f"module_updates: invalid status '{new_status}'")
                continue
            if module.status is ModuleStatus.FROZEN and \
                    target is not ModuleStatus.ACTIVE:
                rep.conflicts.append(
                    f"module '{module.name}' is FROZEN; only unfreeze allowed")
            elif target not in _LEGAL_MODULE.get(module.status, set()) and \
                    target is not module.status:
                rep.conflicts.append(
                    f"module '{module.name}': illegal {module.status.value}"
                    f" -> {target.value}")
            if target is ModuleStatus.IN_COMMAND and actor != "human":
                rep.conflicts.append(
                    f"module '{module.name}': IN_COMMAND requires human actor")
            if module.status is ModuleStatus.COMPLETED and \
                    target is ModuleStatus.ACTIVE:
                rep.warnings.append(f"reopening completed module '{module.name}'")

    for upd in payload.get("task_updates", []):
        tid = str(upd.get("task_id", ""))
        task = project.tasks.get(tid)
        if task is None:
            rep.conflicts.append(f"task_updates: unknown task '{tid}'")
            continue
        new_status = upd.get("status")
        if new_status:
            try:
                target = TaskStatus(new_status)
            except ValueError:
                rep.conflicts.append(f"task_updates: invalid status '{new_status}'")
                continue
            if target is not task.status and \
                    target not in _LEGAL_TASK.get(task.status, set()):
                # the COMMANDER may reopen finished work (rework order) —
                # mirrors module COMPLETED -> ACTIVE "reopen (warned)".
                # Only to READY/NEEDS_VERIFY: RUNNING asserts an agent is
                # actively on it, which a reopen cannot make true.
                if actor == "human" and task.status is TaskStatus.DONE and \
                        target in (TaskStatus.READY, TaskStatus.NEEDS_VERIFY):
                    rep.warnings.append(
                        f"human reopened done task '{task.title}' -> "
                        f"{target.value}")
                else:
                    rep.conflicts.append(
                        f"task '{task.title}': illegal {task.status.value}"
                        f" -> {target.value}")

    new_tasks = payload.get("new_tasks", [])
    if new_tasks:
        hypothetical = dict(project.tasks)
        for i, spec in enumerate(new_tasks):
            if not str(spec.get("title", "")).strip():
                rep.conflicts.append(f"new_tasks[{i}]: missing title")
                continue
            mid = spec.get("module_id", "")
            if mid and mid not in project.modules:
                rep.conflicts.append(f"new_tasks[{i}]: unknown module '{mid}'")
            t = Task(title=spec["title"], role=spec.get("role", "research"),
                     module_id=mid, depends_on=list(spec.get("depends_on", [])))
            for dep in t.depends_on:
                if dep not in hypothetical:
                    rep.conflicts.append(
                        f"new_tasks[{i}]: unknown dependency '{dep}'")
            hypothetical[t.id] = t
        if detect_cycles(hypothetical):
            rep.conflicts.append("new_tasks would create a dependency cycle")

    for upd in payload.get("artifact_updates", []):
        aid = str(upd.get("artifact_id", ""))
        if aid not in project.artifacts:
            rep.conflicts.append(f"artifact_updates: unknown artifact '{aid}'")
        if upd.get("status") is not None:
            from .types import ArtifactStatus
            try:
                ArtifactStatus(upd["status"])
            except ValueError:
                rep.conflicts.append(
                    f"artifact_updates: invalid status '{upd['status']}'")

    for upd in payload.get("risk_updates", []):
        rid = upd.get("risk_id")
        if rid and rid not in project.risks:
            rep.conflicts.append(f"risk_updates: unknown risk '{rid}'")
        if not rid and not str(upd.get("title", "")).strip():
            rep.conflicts.append("risk_updates: new risk needs a title")
        # validate enum values now so apply_delta cannot raise mid-mutation
        if upd.get("level") is not None:
            try:
                RiskLevel(upd["level"])
            except ValueError:
                rep.conflicts.append(
                    f"risk_updates: invalid level '{upd['level']}'")
        if upd.get("status") is not None:
            try:
                RiskStatus(upd["status"])
            except ValueError:
                rep.conflicts.append(
                    f"risk_updates: invalid status '{upd['status']}'")

    for upd in payload.get("assumption_updates", []):
        aid = upd.get("assumption_id")
        if aid and aid not in project.assumptions:
            rep.conflicts.append(f"assumption_updates: unknown assumption '{aid}'")

    if rep.conflicts:
        rep.status = "blocked"
        rep.requires_human = True
    elif rep.warnings:
        rep.status = "warnings"
    return rep


def apply_delta(project: Project, delta: StateDelta, *,
                actor: str = "director") -> CoherenceReport:
    """Coherence-check then mutate. Raises CoherenceBlockedError on conflicts
    (after stamping the delta blocked)."""
    rep = coherence_pass(project, delta, actor=actor)
    if rep.blocked:
        delta.status = "blocked"
        project.deltas[delta.id] = delta
        raise CoherenceBlockedError("; ".join(rep.conflicts))

    payload = delta.payload or {}
    for upd in payload.get("module_updates", []):
        module = project.modules[str(upd["module_id"])]
        if upd.get("status"):
            module.status = ModuleStatus(upd["status"])
        if upd.get("note"):
            module.notes.append(str(upd["note"]))
        module.updated_at = utcnow()

    for upd in payload.get("task_updates", []):
        task = project.tasks[str(upd["task_id"])]
        if upd.get("status"):
            task.status = TaskStatus(upd["status"])
        if upd.get("note"):
            task.result_summary = (task.result_summary + " | " +
                                   str(upd["note"])).strip(" |")
        task.updated_at = utcnow()

    for spec in payload.get("new_tasks", []):
        # delta.trigger is the decision id for decision-deltas (run id / "manual"
        # otherwise). Recording it links a spawned task back to the pick that
        # created it; calibration filters to triggers that are real decisions.
        t = Task(title=spec["title"], role=spec.get("role", "research"),
                 objective=spec.get("objective", spec["title"]),
                 module_id=spec.get("module_id", ""),
                 depends_on=list(spec.get("depends_on", [])),
                 acceptance_criteria=list(spec.get("acceptance_criteria", [])),
                 origin_decision_id=delta.trigger)
        project.tasks[t.id] = t

    for upd in payload.get("risk_updates", []):
        rid = upd.get("risk_id")
        if rid:
            risk = project.risks[rid]
            if upd.get("level"):
                risk.level = RiskLevel(upd["level"])
            if upd.get("status"):
                risk.status = RiskStatus(upd["status"])
            if upd.get("mitigation"):
                risk.mitigation = str(upd["mitigation"])
        else:
            risk = Risk(title=str(upd["title"]),
                        description=str(upd.get("description", "")),
                        level=RiskLevel(upd.get("level", "medium")),
                        mitigation=str(upd.get("mitigation", "")),
                        source=delta.trigger)
            project.risks[risk.id] = risk

    for upd in payload.get("artifact_updates", []):
        art = project.artifacts[str(upd["artifact_id"])]
        if upd.get("status"):
            from .types import ArtifactStatus
            art.status = ArtifactStatus(upd["status"])

    for upd in payload.get("assumption_updates", []):
        aid = upd.get("assumption_id")
        if aid:
            a = project.assumptions[aid]
            if upd.get("status"):
                a.status = str(upd["status"])
            if upd.get("confidence"):
                a.confidence = str(upd["confidence"])
        else:
            a = Assumption(statement=str(upd.get("statement", "")),
                           confidence=str(upd.get("confidence", "medium")))
            project.assumptions[a.id] = a

    for note in payload.get("notes", []):
        # project-level notes ride on the charter constraints? No — keep a
        # lightweight trail on the delta itself; notes are audit material.
        log.info("delta note: %s", note)

    delta.status = "applied"
    delta.applied_at = utcnow()
    project.deltas[delta.id] = delta
    return rep
