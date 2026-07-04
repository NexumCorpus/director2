"""Provenance-preserving compaction for the Claude<->Grok dialogue.

The house pattern (worth promoting everywhere we compress): an immutable RAW archive
+ a lossy WORKING copy. Compaction only ever rewrites WORKING; RAW is never touched,
so every compaction is fully reversible and no turn can be silently dropped.

This tool does the MECHANICAL, checkable parts:
  - snapshot WORKING before touching it (belt-and-suspenders; RAW is the real guard),
  - locate the exact RAW line range the compacted block covers (the citation),
  - splice a caller-supplied summary in place of the oldest exchanges,
  - VERIFY the invariant: every kept-verbatim exchange still exists in RAW, RAW is
    byte-unchanged, and the result is smaller.
The SUMMARY itself is authored by the agent with judgment — a research negotiation
needs a careful, fact/decision/disagreement-preserving summary, not a generic one.

Usage (agent-driven, when the ~120k-char wall warning fires):
  from director.bench.dialogue_compact import compact_working
  compact_working(summary="...the careful summary I wrote...", keep_recent=6)
Self-test:  python -m director.bench.dialogue_compact --selftest
"""
from __future__ import annotations

import pathlib
import re

TRANSCRIPT = pathlib.Path(r"E:\director2\docs\collab\claude-grok\transcript.md")
RAW = pathlib.Path(r"E:\director2\docs\collab\claude-grok\transcript.raw.md")


def split_exchanges(text: str) -> tuple[str, list[str]]:
    """(preamble, [exchange, ...]) — each exchange starts at a '## Claude' header."""
    idxs = [m.start() for m in re.finditer(r"(?m)^## Claude\b", text)]
    if not idxs:
        return text, []
    preamble = text[:idxs[0]]
    bounds = idxs + [len(text)]
    return preamble, [text[bounds[i]:bounds[i + 1]] for i in range(len(idxs))]


def _raw_line_range(raw: str, block: list[str]) -> tuple[int, int]:
    """1-based line range in RAW spanned by the given exchanges (citation pointer)."""
    def anchor(ex: str) -> int:
        key = ex.strip()[:80]
        return raw.find(key)
    first = anchor(block[0])
    last_ex = block[-1].strip()
    last = raw.find(last_ex[:80])
    if first < 0 or last < 0:
        return (0, 0)                       # anchor miss -> caller's verify will catch
    lo = raw[:first].count("\n") + 1
    hi = raw[:last + len(last_ex)].count("\n") + 1
    return (lo, hi)


def compact_working(summary: str, keep_recent: int = 6,
                    working: pathlib.Path = TRANSCRIPT,
                    raw: pathlib.Path = RAW) -> str:
    """Replace the oldest exchanges in WORKING with `summary` (citing the RAW line
    range), keeping the last `keep_recent` verbatim. RAW is never modified. Raises
    if the provenance invariant would be violated."""
    work_text = working.read_text(encoding="utf-8")
    raw_text = raw.read_text(encoding="utf-8")
    preamble, exchanges = split_exchanges(work_text)
    if len(exchanges) <= keep_recent:
        return f"no compaction: {len(exchanges)} exchanges <= keep_recent={keep_recent}"
    old, recent = exchanges[:-keep_recent], exchanges[-keep_recent:]

    # provenance precheck: every CURRENT working exchange must exist verbatim in RAW.
    for ex in exchanges:
        if ex.strip() not in raw_text:
            raise AssertionError(
                "provenance gap: a working exchange is not present in RAW — refusing "
                "to compact (RAW must be able to reconstruct everything).")

    lo, hi = _raw_line_range(raw_text, old)
    summary_block = (
        f"## [COMPACTED — {len(old)} earlier exchanges]\n"
        f"_Lossy summary. Verbatim originals are in `transcript.raw.md` "
        f"lines {lo}-{hi}; RAW is the source of truth and is never compressed._\n\n"
        f"{summary.strip()}\n")
    new_text = preamble + "\n\n" + summary_block + "".join(recent)

    # snapshot WORKING before overwrite (RAW is the real guarantee; this is extra).
    working.with_name(working.stem + ".pre-compact.md").write_text(
        work_text, encoding="utf-8")

    # post-verify the invariant BEFORE committing the write.
    assert raw.read_text(encoding="utf-8") == raw_text, "RAW changed during compaction!"
    for ex in recent:
        assert ex.strip() in raw_text, "kept exchange missing from RAW"
        assert ex in new_text, "kept exchange not verbatim in new working copy"
    assert len(new_text) < len(work_text), "compaction did not reduce size"

    working.write_text(new_text, encoding="utf-8")
    return (f"compacted {len(old)} exchanges -> summary (RAW lines {lo}-{hi}); "
            f"kept {len(recent)} verbatim; {len(work_text)}->{len(new_text)} chars; "
            f"RAW untouched")


def _selftest() -> None:                                  # pragma: no cover (manual)
    import tempfile
    d = pathlib.Path(tempfile.mkdtemp(prefix="compact_"))
    w, r = d / "work.md", d / "raw.md"
    turns = []
    for i in range(12):
        turns.append(f"\n\n## Claude\nmessage number {i} with unique token Z{i}Q\n\n"
                     f"## Grok  _(grok-build, {i}.0s)_\nreply number {i} token Y{i}P\n")
    body = "".join(turns)
    w.write_text(body, encoding="utf-8")
    r.write_text("# RAW archive\n" + body, encoding="utf-8")
    raw_before = r.read_text(encoding="utf-8")
    msg = compact_working("SUMMARY: turns 0-5 established X, disagreed on Y, "
                          "resolved Z.", keep_recent=6, working=w, raw=r)
    print(msg)
    new = w.read_text(encoding="utf-8")
    # invariants
    assert r.read_text(encoding="utf-8") == raw_before, "RAW must be untouched"
    assert "COMPACTED" in new and "lines" in new, "summary block + citation present"
    for i in range(6, 12):                                # recent 6 verbatim
        assert f"Z{i}Q" in new and f"Y{i}P" in new, f"recent turn {i} must be verbatim"
    for i in range(0, 6):                                 # old 6 compacted out
        assert f"Z{i}Q" not in new, f"old turn {i} should be summarized away"
        assert f"Z{i}Q" in raw_before, f"old turn {i} must still live in RAW"
    assert len(new) < len(body), "must shrink"
    print("SELFTEST OK: RAW untouched, recent verbatim, old reconstructable from RAW, "
          "size reduced.")


if __name__ == "__main__":                                # pragma: no cover
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
