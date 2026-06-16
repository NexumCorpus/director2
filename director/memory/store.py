"""MemoryStore — persistent cross-project notes with vector recall.

Each note is one JSON file under ``<home>/memory/notes/`` (human-inspectable,
git-friendly) plus an entry in the vector index for semantic recall. This is
the framework's long-term memory; project state lives in ProjectStore.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from ..core.types import new_id, utcnow
from ..logging_setup import get_logger
from .vector import VectorStore

log = get_logger("memory")


class MemoryStore:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.notes_dir = cfg.memory_dir / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.index = VectorStore(cfg.memory_dir / "vector_index.json",
                                 dims=cfg.vector_dims)

    def remember(self, text: str, *, kind: str = "note",
                 tags: list[str] | None = None, source: str = "") -> str:
        note_id = new_id()
        note = {"id": note_id, "kind": kind, "text": text,
                "tags": tags or [], "source": source,
                "created_at": utcnow().isoformat()}
        path = self.notes_dir / f"{note_id}.json"
        path.write_text(json.dumps(note, indent=2), encoding="utf-8")
        self.index.add(note_id, text, {"kind": kind, "tags": tags or [],
                                       "source": source})
        log.info("remembered %s (%s): %s", note_id, kind, text[:80])
        return note_id

    def recall(self, query: str, k: int | None = None) -> list[dict]:
        hits = self.index.search(query, k or self.cfg.memory_recall_k,
                                 min_score=0.05)
        out = []
        for h in hits:
            note = self.get(h["id"])
            if note:
                note["score"] = h["score"]
                out.append(note)
        return out

    def get(self, note_id: str) -> dict | None:
        path = self.notes_dir / f"{note_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def forget(self, note_id: str) -> bool:
        path = self.notes_dir / f"{note_id}.json"
        removed = False
        if path.is_file():
            path.unlink()
            removed = True
        self.index.remove(note_id)
        return removed

    def all_notes(self) -> list[dict]:
        notes = []
        for p in sorted(self.notes_dir.glob("*.json")):
            try:
                notes.append(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return notes

    def __len__(self) -> int:
        return len(self.index)
