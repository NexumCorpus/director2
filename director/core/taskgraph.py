"""Task graph operations: dependency resolution, readiness, cycles,
milestones, and the risk register. Pure functions over a Project — no IO.
"""

from __future__ import annotations

from ..logging_setup import get_logger
from .types import (Milestone, MilestoneStatus, Project, Risk, Task,
                    TaskStatus, utcnow)

log = get_logger("taskgraph")

_TERMINAL = {TaskStatus.DONE, TaskStatus.CANCELLED}
_RUNNABLE = {TaskStatus.PENDING, TaskStatus.READY}


def detect_cycles(tasks: dict[str, Task]) -> list[list[str]]:
    """Return one representative cycle per strongly-connected loop found."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}
    cycles: list[list[str]] = []

    def dfs(tid: str, stack: list[str]) -> None:
        color[tid] = GRAY
        stack.append(tid)
        for dep in tasks[tid].depends_on:
            if dep not in tasks:
                continue
            if color[dep] == GRAY:
                i = stack.index(dep)
                cycles.append(stack[i:] + [dep])
            elif color[dep] == WHITE:
                dfs(dep, stack)
        stack.pop()
        color[tid] = BLACK

    for tid in tasks:
        if color[tid] == WHITE:
            dfs(tid, [])
    return cycles


def deps_satisfied(project: Project, task: Task) -> bool:
    for dep in task.depends_on:
        dep_task = project.tasks.get(dep)
        if dep_task is None:
            log.warning("task %s depends on unknown task %s", task.id, dep)
            return False
        if dep_task.status is not TaskStatus.DONE:
            return False
    return True


def refresh_statuses(project: Project) -> int:
    """PENDING→READY when deps are met; READY→PENDING if a dep regressed.
    Returns number of transitions."""
    flips = 0
    for task in project.tasks.values():
        if task.status is TaskStatus.PENDING and deps_satisfied(project, task):
            task.status = TaskStatus.READY
            task.updated_at = utcnow()
            flips += 1
        elif task.status is TaskStatus.READY and not deps_satisfied(project, task):
            task.status = TaskStatus.PENDING
            task.updated_at = utcnow()
            flips += 1
    return flips


def ready_tasks(project: Project, *, limit: int | None = None) -> list[Task]:
    """Runnable tasks in stable (created_at, id) order, deps satisfied."""
    out = [t for t in project.tasks.values()
           if t.status in _RUNNABLE and deps_satisfied(project, t)]
    out.sort(key=lambda t: (t.created_at, t.id))
    return out[:limit] if limit else out


# roles whose results are real only if persisted as artifacts (mirrors the
# artifact-grounding gate in verify/evaluators.py — incl. synthesis, which
# produces a deliverable; the finalize CALL is not a graph task so is unaffected)
_ARTIFACT_BEARING_ROLES = {"code", "simulation", "synthesis"}


def milestone_blockers(project: Project, ms: Milestone) -> list[str]:
    """Why a milestone is NOT reached (empty list == reachable). Live finding
    (2026-06-12): milestones flipped 'reached' off task-done counts while the
    named deliverable artifact never existed — a task force-closed 'done' by
    a packet delta counted the same as one that delivered. A milestone now
    requires every member DONE and every artifact-bearing member (code /
    simulation) to actually carry artifacts."""
    blockers = []
    for tid in ms.task_ids:
        t = project.tasks.get(tid)
        if t is None:
            blockers.append(f"member task {tid} does not exist")
        elif t.status is not TaskStatus.DONE:
            blockers.append(f"'{t.title}' is {t.status.value}")
        elif t.role in _ARTIFACT_BEARING_ROLES and not t.artifact_ids:
            blockers.append(f"'{t.title}' ({t.role}) is done but delivered "
                            f"no artifacts - result is ungrounded")
    return blockers


def refresh_milestones(project: Project) -> list[Milestone]:
    """Mark milestones REACHED when every member task is DONE and every
    artifact-bearing member actually delivered artifacts. Returns newly
    reached milestones; held-back milestones are logged with their blockers."""
    reached = []
    for ms in project.milestones.values():
        if not ms.task_ids:
            continue
        blockers = milestone_blockers(project, ms)
        if ms.status is MilestoneStatus.PENDING:
            if not blockers:
                ms.status = MilestoneStatus.REACHED
                reached.append(ms)
            elif all("is done but delivered no artifacts" in b
                     for b in blockers):
                # all tasks done, only grounding missing — say so loudly
                log.warning("milestone '%s' held back: %s",
                            ms.name, "; ".join(blockers))
        elif ms.status is MilestoneStatus.REACHED and blockers:
            # a member was reopened or regressed — the milestone reverts
            # rather than asserting a deliverable that no longer holds
            ms.status = MilestoneStatus.PENDING
            project.milestone_reverts += 1     # charter_integrity signal (Body reads it)
            log.warning("milestone '%s' reverted to pending: %s",
                        ms.name, "; ".join(blockers))
    return reached


def open_risks(project: Project) -> list[Risk]:
    from .types import RiskStatus
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out = [r for r in project.risks.values()
           if r.status in (RiskStatus.OPEN, RiskStatus.MITIGATING)]
    out.sort(key=lambda r: order.get(r.level.value, 9))
    return out


def graph_summary(project: Project) -> dict:
    counts: dict[str, int] = {}
    for t in project.tasks.values():
        counts[t.status.value] = counts.get(t.status.value, 0) + 1
    return {
        "tasks_total": len(project.tasks),
        "tasks_by_status": counts,
        "milestones": {m.name: m.status.value for m in project.milestones.values()},
        "open_risks": len(open_risks(project)),
        "open_packets": sum(1 for p in project.packets.values()
                            if p.status.value == "presented"),
        "done": counts.get("done", 0),
        "blocked": counts.get("blocked", 0) + counts.get("needs_verify", 0),
    }
