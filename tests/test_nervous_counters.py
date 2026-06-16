"""Inert signal counters: milestone_reverts (taskgraph) + coherence_blocks (coherence)."""

import pytest

from director.core.coherence import apply_delta
from director.core.taskgraph import refresh_milestones, refresh_statuses
from director.core.types import (
    Milestone, MilestoneStatus, Module, ModuleStatus, ModuleType, Project,
    StateDelta, Task, TaskStatus,
)
from director.errors import CoherenceBlockedError


def _project_with_reached_milestone() -> Project:
    p = Project(name="rev")
    m = Module(name="core", type=ModuleType.IMPLEMENTATION, purpose="x",
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    t = Task(title="deliver", role="research", module_id=m.id,
             status=TaskStatus.DONE, artifact_ids=[])
    p.tasks[t.id] = t
    ms = Milestone(name="M0", task_ids=[t.id], status=MilestoneStatus.PENDING)
    p.milestones[ms.id] = ms
    reached = refresh_milestones(p)
    assert ms.status is MilestoneStatus.REACHED
    assert reached and reached[0].id == ms.id
    return p


def test_milestone_revert_increments_counter():
    p = _project_with_reached_milestone()
    assert p.milestone_reverts == 0
    t = next(iter(p.tasks.values()))
    t.status = TaskStatus.READY
    refresh_milestones(p)
    ms = next(iter(p.milestones.values()))
    assert ms.status is MilestoneStatus.PENDING
    assert p.milestone_reverts == 1


def test_milestone_revert_counter_inert_when_no_revert():
    p = _project_with_reached_milestone()
    refresh_milestones(p)
    assert p.milestone_reverts == 0


def _blocking_delta() -> StateDelta:
    return StateDelta(
        trigger="manual", summary="bad module update",
        payload={"module_updates": [
            {"module_id": "does-not-exist", "status": "in_command"}]})


def test_coherence_block_increments_counter():
    p = Project(name="coh")
    assert p.coherence_blocks == 0
    with pytest.raises(CoherenceBlockedError):
        apply_delta(p, _blocking_delta(), actor="human")
    assert p.coherence_blocks == 1


def test_coherence_block_counter_inert_on_clean_delta():
    p = Project(name="coh2")
    m = Module(name="core", type=ModuleType.IMPLEMENTATION, purpose="x",
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(
        trigger="manual", summary="clean note",
        payload={"module_updates": [{"module_id": m.id, "note": "ok"}]})
    apply_delta(p, delta, actor="human")
    assert p.coherence_blocks == 0
