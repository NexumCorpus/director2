"""Domain hooks — pluggable domain packs.

A hook contributes four things to the framework:
  * task templates  — domain tasks injectable into any project
  * verifiers       — trusted-code checks registered under stable names
  * scaffolds       — starter artifacts written to disk
  * discovery domains (optional) — problems for the improvement loop

Hooks keep Director generic: game modding and defense modeling live here, not
in the core.
"""

from __future__ import annotations

from typing import Protocol

from ..core.types import Module, ModuleStatus, ModuleType, Project, Task
from ..logging_setup import get_logger
from ..verify import VerifierRegistry

log = get_logger("hooks")


class DomainHook(Protocol):
    name: str
    description: str

    def task_templates(self) -> list[dict]: ...
    def verifiers(self) -> dict: ...                 # name -> factory
    def scaffold(self, target_dir, **params) -> list: ...


_HOOKS: dict[str, type] = {}


def register_hook(hook_cls: type) -> None:
    _HOOKS[hook_cls.name] = hook_cls


def get_hook(name: str) -> DomainHook:
    if name not in _HOOKS:
        raise KeyError(f"unknown hook '{name}' (known: {sorted(_HOOKS)})")
    return _HOOKS[name]()


def hook_names() -> list[str]:
    return sorted(_HOOKS)


def register_hook_verifiers(registry: VerifierRegistry,
                            hook: DomainHook) -> list[str]:
    names = []
    for name, factory in hook.verifiers().items():
        registry.register(name, factory)
        names.append(name)
    return names


def inject_hook_tasks(project: Project, hook: DomainHook) -> list[Task]:
    """Create a module for the hook and add its template tasks (dependencies
    wired by template order index)."""
    module = Module(name=f"{hook.name} work", type=ModuleType.IMPLEMENTATION,
                    purpose=hook.description, status=ModuleStatus.ACTIVE)
    project.modules[module.id] = module
    created: list[Task] = []
    for tpl in hook.task_templates():
        deps = [created[i].id for i in tpl.get("depends_on_index", [])
                if 0 <= i < len(created)]
        task = Task(
            title=tpl["title"], role=tpl.get("role", "research"),
            objective=tpl.get("objective", tpl["title"]),
            module_id=module.id, depends_on=deps,
            context=tpl.get("context", ""),
            acceptance_criteria=list(tpl.get("acceptance_criteria", [])),
            verifiers=["agent_output"] + list(tpl.get("verifiers", [])),
            properties=list(tpl.get("properties", [])))
        project.tasks[task.id] = task
        created.append(task)
    log.info("hook '%s' injected %d tasks into project %s",
             hook.name, len(created), project.id)
    return created
