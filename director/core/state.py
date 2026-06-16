"""Event-sourced file persistence — no database required.

Each project lives at ``<home>/projects/<id>/``:

* ``project.json``  — the authoritative snapshot (atomic write: tmp + replace)
* ``journal.jsonl`` — append-only audit journal (every AuditEvent, every delta)
* ``artifacts/``    — artifacts mirrored to individual files for human browsing

The snapshot is the source of truth for *state*; the journal is the source of
truth for *history*. A crash between journal-append and snapshot-save loses at
most the in-flight mutation, never history. (Layered-auditability lesson from
Director 1.0 dogfooding.)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from ..config import Config
from ..errors import NotFoundError, StateError
from ..logging_setup import get_logger
from .types import (Artifact, AuditEvent, Project, decode, encode, utcnow)

log = get_logger("state")

_ARTIFACT_EXT = {
    "code": ".py", "json": ".json", "markdown": ".md", "report": ".md",
    "dialogue": ".json", "quest": ".json", "sim": ".json",
}


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class ProjectStore:
    """All reads and writes for projects. One instance per Config/workspace."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        cfg.ensure_dirs()

    # ------------------------------------------------------------------ paths
    def project_dir(self, project_id: str) -> Path:
        return self.cfg.projects_dir / project_id

    def _snapshot_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def _journal_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "journal.jsonl"

    # ------------------------------------------------------------------ CRUD
    def create(self, name: str) -> Project:
        project = Project(name=name)
        pdir = self.project_dir(project.id)
        if pdir.exists():
            raise StateError(f"project dir already exists: {pdir}")
        (pdir / "artifacts").mkdir(parents=True)
        self.save(project)
        self.append_event(project.id, AuditEvent(
            type="project.created", summary=f"Project '{name}' created",
            payload={"project_id": project.id}))
        self.set_current(project.id)
        log.info("created project %s (%s)", project.id, name)
        return project

    def save(self, project: Project) -> None:
        project.updated_at = utcnow()
        path = self._snapshot_path(project.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(path, json.dumps(encode(project), indent=2))

    def load(self, project_ref: str) -> Project:
        """Load by exact id or unique prefix."""
        pid = self._resolve(project_ref)
        path = self._snapshot_path(pid)
        if not path.is_file():
            raise NotFoundError(f"no snapshot for project {pid}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return decode(Project, data)

    def _resolve(self, ref: str) -> str:
        if not ref:
            raise NotFoundError("empty project reference")
        root = self.cfg.projects_dir
        if (root / ref).is_dir():
            return ref
        matches = [d.name for d in root.iterdir()
                   if d.is_dir() and d.name.startswith(ref)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise NotFoundError(f"no project matching '{ref}'")
        raise StateError(f"ambiguous project ref '{ref}': {matches}")

    def list_projects(self) -> list[dict]:
        out = []
        if not self.cfg.projects_dir.is_dir():
            return out
        for d in sorted(self.cfg.projects_dir.iterdir()):
            snap = d / "project.json"
            if not snap.is_file():
                continue
            try:
                data = json.loads(snap.read_text(encoding="utf-8"))
                out.append({
                    "id": data.get("id", d.name),
                    "name": data.get("name", "?"),
                    "status": data.get("status", "?"),
                    "updated_at": data.get("updated_at", ""),
                    "tasks": len(data.get("tasks", {})),
                    "open_packets": sum(
                        1 for p in data.get("packets", {}).values()
                        if p.get("status") == "presented"),
                })
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("skipping unreadable project %s: %s", d.name, exc)
        return out

    # ---------------------------------------------------------------- journal
    def append_event(self, project_id: str, event: AuditEvent) -> AuditEvent:
        path = self._journal_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(encode(event)) + "\n")
        return event

    def journal(self, project_id: str, *, limit: int | None = None) -> Iterator[AuditEvent]:
        path = self._journal_path(self._resolve(project_id))
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if limit:
            lines = lines[-limit:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                yield decode(AuditEvent, json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                log.warning("bad journal line skipped: %s", exc)

    # --------------------------------------------------------------- artifacts
    def mirror_artifact(self, project_id: str, artifact: Artifact) -> Path:
        """Write artifact content to a real file so a human can open it."""
        ext = _ARTIFACT_EXT.get(artifact.kind, ".txt")
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "_"
                             for c in artifact.title)[:48].strip().replace(" ", "-")
        path = self.project_dir(project_id) / "artifacts" / f"{artifact.id}-{safe_title}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
        return path

    # ----------------------------------------------------------- current ptr
    def set_current(self, project_id: str) -> None:
        _atomic_write_text(self.cfg.home / "current.json",
                           json.dumps({"project_id": project_id}))

    def get_current(self) -> str | None:
        path = self.cfg.home / "current.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("project_id")
        except (json.JSONDecodeError, OSError):
            return None
