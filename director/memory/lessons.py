"""LessonLedger — the self-improvement memory.

Agents and improvement-loop runs emit lessons ("what we learned"); the ledger
deduplicates near-identical lessons (vector similarity), persists them as
JSONL, and produces a bounded digest that the runner injects into every agent
prompt. This closes the experience loop: yesterday's failure shapes today's
prompt — with bounded context (RDE's memory-pruning principle).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from ..config import Config
from ..core.types import Lesson, utcnow
from ..logging_setup import get_logger
from .vector import VectorStore

log = get_logger("memory.lessons")

_DEDUPE_SIM = 0.95


class LessonLedger:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.path = cfg.memory_dir / "lessons.jsonl"
        self.index = VectorStore(cfg.memory_dir / "lessons_index.json",
                                 dims=cfg.vector_dims)

    def add(self, text: str, *, context: str = "", source: str = "",
            tags: list[str] | None = None) -> Lesson | None:
        """Record a lesson; returns None if a near-duplicate already exists."""
        text = text.strip()
        if not text:
            return None
        if len(self.index) and self.index.max_similarity(text) >= _DEDUPE_SIM:
            log.debug("lesson deduped: %s", text[:60])
            return None
        lesson = Lesson(text=text, context=context, source=source,
                        tags=tags or [])
        row = asdict(lesson)
        row["created_at"] = lesson.created_at.isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        self.index.add(lesson.id, text, {"tags": lesson.tags,
                                         "source": source})
        return lesson

    def all(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def digest(self, query: str = "", *, max_items: int | None = None) -> str:
        """Bounded bullet list for prompt injection. With a query, the most
        relevant lessons; otherwise the most recent."""
        cap = max_items or self.cfg.lessons_digest_max
        if query and len(self.index):
            hits = self.index.search(query, cap, min_score=0.05)
            lines = [f"- {h['text']}" for h in hits]
        else:
            lines = [f"- {row['text']}" for row in self.all()[-cap:]]
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.index)
