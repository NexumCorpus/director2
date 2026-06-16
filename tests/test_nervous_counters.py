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
