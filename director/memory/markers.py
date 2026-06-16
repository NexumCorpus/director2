"""Gut Markers — persistent, un-gameable memory of failure (nervous-system v2).

A ``Marker`` is a SCAR: a diagnosis (failing case + cause) plus a trusted-only
signed ``weight`` (< 0 repels). Trusted code computes the weight from executed
outcomes; the only field a generator ever reads is ``diagnosis`` (problems, not
numbers — Constitution #3). The store reuses the pure-Python ``VectorStore`` (no
model) as a SIBLING to the lesson ledger, and MERGES-and-strengthens a recurring
scar instead of the lesson ledger's silent ``_DEDUPE_SIM`` drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core.types import new_id, utcnow
from .vector import VectorStore


def task_signature(task) -> str:
    """Stable recall key: role | module | normalized objective (or title)."""
    obj = (task.objective or task.title or "").strip().lower()
    return f"{task.role}|{task.module_id}|{obj}"


@dataclass
class Marker:
    signature: str
    cause: str = "failed_verification"   # failed_verification | grounding_damage | charter_breach | ...
    diagnosis: str = ""                  # the ONLY model-facing field (problems, not numbers)
    weight: float = 0.0                  # signed, trusted-only: < 0 repels (hurt before)
    count: int = 1                       # times this scar recurred (merge-and-strengthen)
    origin: str = ""                     # origin_decision_id, or synthetic "plan:<module>"
    last_cycle: int = 0
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)


class MarkerStore:
    """VectorStore-backed marker index. Text indexed = the signature (recall key);
    weight/diagnosis/etc live in the row meta."""

    def __init__(self, cfg):
        self.cfg = cfg
        path = Path(cfg.marker_store_path) if cfg.marker_store_path \
            else cfg.memory_dir / "markers_index.json"
        self.index = VectorStore(path, dims=cfg.vector_dims)

    def record(self, marker: Marker) -> Marker:
        """Insert a new scar, or MERGE-and-strengthen an existing one for the same
        signature (cosine >= cfg.marker_merge_sim). Trusted-only; never a model call."""
        hits = self.index.search(marker.signature, k=1,
                                 min_score=self.cfg.marker_merge_sim)
        if hits:
            ex = hits[0]
            meta = dict(ex["meta"])
            meta["weight"] = max(self.cfg.marker_repel_floor,
                                 float(meta.get("weight", 0.0))
                                 - self.cfg.marker_repel_step)
            meta["count"] = int(meta.get("count", 1)) + 1
            meta["diagnosis"] = marker.diagnosis or meta.get("diagnosis", "")
            meta["cause"] = marker.cause
            meta["last_cycle"] = marker.last_cycle
            self.index.add(ex["id"], marker.signature, meta)   # re-add under same id
            return self._to_marker(ex["id"], marker.signature, meta)
        marker.weight = -self.cfg.marker_repel_step
        meta = {"weight": marker.weight, "count": 1, "diagnosis": marker.diagnosis,
                "cause": marker.cause, "origin": marker.origin,
                "last_cycle": marker.last_cycle}
        self.index.add(marker.id, marker.signature, meta)
        return marker

    def recall(self, signature: str, *, k: int | None = None,
               min_sim: float | None = None) -> list[Marker]:
        """Markers whose signature is cosine >= cfg.marker_recall_sim of ``signature``."""
        hits = self.index.search(
            signature, k=k or self.cfg.marker_digest_max,
            min_score=self.cfg.marker_recall_sim if min_sim is None else min_sim)
        return [self._to_marker(h["id"], h["text"], h["meta"]) for h in hits]

    @staticmethod
    def _to_marker(id_: str, signature: str, meta: dict) -> Marker:
        return Marker(signature=signature, cause=meta.get("cause", ""),
                      diagnosis=meta.get("diagnosis", ""),
                      weight=float(meta.get("weight", 0.0)),
                      count=int(meta.get("count", 1)),
                      origin=meta.get("origin", ""),
                      last_cycle=int(meta.get("last_cycle", 0)), id=id_)
