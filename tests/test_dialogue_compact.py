"""Provenance-invariant guard for the Claude<->Grok dialogue compactor.

The one property that must never regress: compacting the WORKING transcript can
never lose data, because the RAW archive is immutable and reconstructs everything.
"""
from __future__ import annotations

import pytest

from director.bench.dialogue_compact import compact_working, split_exchanges


def _make(tmp_path, n: int):
    turns = []
    for i in range(n):
        turns.append(f"\n\n## Claude\nmessage {i} token Z{i}Q\n\n"
                     f"## Grok  _(grok-build, {i}.0s)_\nreply {i} token Y{i}P\n")
    body = "".join(turns)
    w, r = tmp_path / "work.md", tmp_path / "raw.md"
    w.write_text(body, encoding="utf-8")
    r.write_text("# RAW archive\n" + body, encoding="utf-8")
    return w, r, body


def test_compaction_preserves_provenance(tmp_path):
    w, r, body = _make(tmp_path, 12)
    raw_before = r.read_text(encoding="utf-8")
    compact_working("summary of the first six exchanges", keep_recent=6,
                    working=w, raw=r)
    new = w.read_text(encoding="utf-8")
    # RAW is byte-identical (the guarantee)
    assert r.read_text(encoding="utf-8") == raw_before
    # the recent 6 survive verbatim in WORKING; the old 6 are summarized out but
    # still fully present in RAW (reconstructable)
    for i in range(6, 12):
        assert f"Z{i}Q" in new and f"Y{i}P" in new
    for i in range(6):
        assert f"Z{i}Q" not in new
        assert f"Z{i}Q" in raw_before
    # citation + shrink
    assert "COMPACTED" in new and "lines" in new
    assert len(new) < len(body)


def test_refuses_when_working_diverges_from_raw(tmp_path):
    # if WORKING holds an exchange RAW lacks, compaction must REFUSE (can't lose it)
    w, r, body = _make(tmp_path, 10)
    w.write_text(body + "\n\n## Claude\norphan not-in-raw token QQQ\n\n"
                        "## Grok  _(grok-build, 9.0s)_\norphan reply\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        compact_working("s", keep_recent=4, working=w, raw=r)


def test_noop_when_at_or_below_keep_recent(tmp_path):
    w, r, _ = _make(tmp_path, 4)
    before = w.read_text(encoding="utf-8")
    msg = compact_working("s", keep_recent=6, working=w, raw=r)
    assert "no compaction" in msg
    assert w.read_text(encoding="utf-8") == before        # untouched


def test_split_exchanges_counts_correctly(tmp_path):
    _, _, body = _make(tmp_path, 5)
    preamble, ex = split_exchanges(body)
    assert len(ex) == 5
    assert all(e.lstrip().startswith("## Claude") for e in ex)
