"""Pure-Python vector store: signed feature hashing over words + character
trigrams, cosine retrieval, JSON persistence.

Deliberately dependency-free and deterministic: recall quality is "good
enough" for note/lesson retrieval, runs offline, and never drifts between
machines. The embedding is a fixed function — no model, no network. Swap in a
real embedding backend later behind the same add/search API if needed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from pathlib import Path

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    text = text.lower()
    words = _WORD_RE.findall(text)
    toks = list(words)
    for w in words:
        if len(w) > 3:
            toks.extend(w[i:i + 3] for i in range(len(w) - 2))
    return toks


def embed(text: str, dims: int = 256) -> list[float]:
    """Signed hashed bag-of-features, L2-normalized. Deterministic."""
    vec = [0.0] * dims
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big")
        idx = h % dims
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    """id → (vector, text, meta). Persists to one JSON file, atomically."""

    def __init__(self, path: Path, dims: int = 256):
        self.path = Path(path)
        self.dims = dims
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.dims = int(data.get("dims", self.dims))
            self._rows = data.get("rows", {})
        except (json.JSONDecodeError, OSError):
            self._rows = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Unique tmp per process+thread so concurrent saves can't clobber one
        # another's tmp file before the os.replace.
        tmp = self.path.with_suffix(
            f".{os.getpid()}.{threading.get_ident()}.tmp")
        with self._lock:
            tmp.write_text(json.dumps({"dims": self.dims, "rows": self._rows}),
                           encoding="utf-8")
            os.replace(tmp, self.path)

    def add(self, id_: str, text: str, meta: dict | None = None,
            *, persist: bool = True) -> None:
        with self._lock:
            self._rows[id_] = {"vec": embed(text, self.dims),
                               "text": text, "meta": meta or {}}
        if persist:
            self.save()

    def remove(self, id_: str, *, persist: bool = True) -> bool:
        with self._lock:
            existed = self._rows.pop(id_, None) is not None
        if existed and persist:
            self.save()
        return existed

    def search(self, query: str, k: int = 5,
               *, min_score: float = 0.0) -> list[dict]:
        qv = embed(query, self.dims)
        scored = []
        for id_, row in self._rows.items():
            s = cosine(qv, row["vec"])
            if s >= min_score:
                scored.append({"id": id_, "score": round(s, 4),
                               "text": row["text"], "meta": row["meta"]})
        scored.sort(key=lambda r: -r["score"])
        return scored[:k]

    def max_similarity(self, text: str) -> float:
        qv = embed(text, self.dims)
        return max((cosine(qv, row["vec"]) for row in self._rows.values()),
                   default=0.0)

    def __len__(self) -> int:
        return len(self._rows)

    def __contains__(self, id_: str) -> bool:
        return id_ in self._rows
