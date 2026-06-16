"""Structural novelty — is this candidate genuinely new, or a prior approach
in disguise? (Ported from RDE's fingerprint machinery.)

Fingerprints hash the *AST shape* (node-type walk), so whitespace and renaming
don't fool it. Similarity uses a sequence ratio over node-type streams; above
``threshold`` the candidate is flagged a structural recombination.

Per the constitution this is an **alignable** metric: it steers and labels, it
never gates a correctness claim.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher


def node_sequence(code: str) -> list[str]:
    """Stable stream of AST node type names (empty on syntax error)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [type(n).__name__ for n in ast.walk(tree)]


def fingerprint(code: str) -> str:
    seq = node_sequence(code)
    return hashlib.sha256("|".join(seq).encode("utf-8")).hexdigest()[:16]


def similarity(seq_a: list[str], seq_b: list[str]) -> float:
    if not seq_a or not seq_b:
        return 0.0
    return SequenceMatcher(None, seq_a, seq_b).ratio()


@dataclass
class NoveltyReport:
    novel: bool = True
    max_similarity: float = 0.0
    closest_id: str = ""
    fingerprint: str = ""
    identical: bool = False
    details: dict = field(default_factory=dict)


def assess_novelty(code: str, priors: dict[str, list[str]], *,
                   threshold: float = 0.85) -> NoveltyReport:
    """Compare candidate code against prior node sequences (id → sequence)."""
    fp = fingerprint(code)
    seq = node_sequence(code)
    best_id, best_sim = "", 0.0
    for pid, pseq in priors.items():
        sim = similarity(seq, pseq)
        if sim > best_sim:
            best_id, best_sim = pid, sim
    return NoveltyReport(
        novel=best_sim < threshold,
        max_similarity=round(best_sim, 4),
        closest_id=best_id,
        fingerprint=fp,
        identical=best_sim >= 0.9999,
    )
