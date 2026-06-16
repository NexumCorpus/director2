"""Terminal dashboard — a dependency-free ANSI renderer over the SAME read model
the web dashboard serves (digest / overview).

No curses (absent from Windows stdlib); just ANSI strings, so every renderer is a
PURE function (dict -> str) and unit-testable. ``director tui`` prints a snapshot;
``--watch N`` repaints every N seconds. The verification honesty carries over from
the web UI: VERIFIED (green) vs TRUSTED-partial (amber) vs Judged — never a green
check over nothing.
"""

from __future__ import annotations

_CODES = {"reset": "0", "bold": "1", "dim": "2", "red": "31", "green": "32",
          "yellow": "33", "blue": "34", "magenta": "35", "cyan": "36",
          "grey": "90"}


def paint(s: str, *styles: str, color: bool = True) -> str:
    if not color or not styles:
        return s
    codes = ";".join(_CODES[s] for s in styles if s in _CODES)
    return f"\x1b[{codes}m{s}\x1b[0m" if codes else s


def _outcome(o: dict, color: bool) -> str:
    """Mirror the web outcome cell: the honest verification tier of an option."""
    k = o.get("check") or "none"
    sc = o.get("check_score")
    sc = "" if sc is None else f"{sc:g}"
    if k == "verified":
        return paint(f"VERIFIED {sc or '✓'}", "green", "bold", color=color)
    if k == "verified_partial":
        n, m = o.get("sub_claims_verified", 0), o.get("sub_claims_total", 0)
        return paint(f"TRUSTED {n}/{m}", "yellow", color=color)
    if k == "judged":
        return paint(f"judged {sc or '~'}", "grey", color=color)
    return paint("—", "grey", color=color)


def render_overview(ov: dict, *, color: bool = True) -> str:
    lines = [paint(f"DIRECTOR · backend {ov.get('backend', '?')}", "bold",
                   color=color)]
    projs = ov.get("projects", [])
    if not projs:
        lines.append(paint("  (no projects — `director new \"...\"`)", "grey",
                           color=color))
    for p in projs:
        op = p.get("open_packets", 0)
        flag = paint(f" ⚑ {op} awaits", "yellow", color=color) if op else ""
        cur = "▶ " if p.get("id") == ov.get("current") else "  "
        lines.append(f"{cur}{p.get('id', '?')[:12]}  "
                     f"[{p.get('status', '?'):>9}]  {p.get('name', '?')}{flag}")
    return "\n".join(lines)


def render_project(d: dict, *, color: bool = True) -> str:
    name = d.get("name", "?")
    lines = [paint(f"══ {name}  [{d.get('status', '?')}]", "bold", "cyan",
                   color=color)]
    rk = d.get("conviction_rank") or {}
    persona = d.get("conviction_read", "")
    if rk.get("rank"):
        persona += f"  ·  {rk.get('conviction', '')} {rk.get('rank_name', '')}"
    if persona:
        lines.append(paint("  " + persona, "dim", color=color))
    if d.get("conviction_calibration"):
        lines.append(paint("  " + d["conviction_calibration"], "grey",
                           color=color))
    ig = d.get("integrity") or {}
    viol = ig.get("violations", 0)
    pd = ig.get("partial_deliverables", 0)
    okn = (ig.get("reports") or {}).get("ok", 0)
    vh = (paint(f"  ⚠ {viol} TAMPERED report(s)", "red", "bold", color=color)
          if viol else
          paint(f"  ⊨ {pd} trusted deliverable(s) · {okn} signed report(s) "
                f"intact", "grey", color=color))
    lines.append(vh)
    s = d.get("summary") or {}
    bs = s.get("tasks_by_status") or {}
    lines.append(f"  tasks {s.get('done', 0)}/{s.get('tasks_total', 0)} done"
                 f" · {bs.get('running', 0)} running"
                 f" · {s.get('blocked', 0)} blocked")
    lad = d.get("ladder") or {}
    if isinstance(lad, dict) and sum(lad.values()):
        bits = []
        if lad.get("verified"):
            bits.append(paint(f"{lad['verified']} verified", "green",
                              color=color))
        if lad.get("verified_partial"):
            bits.append(paint(f"{lad['verified_partial']} trusted", "yellow",
                              color=color))
        if lad.get("judged"):
            bits.append(paint(f"{lad['judged']} judged", "grey", color=color))
        if lad.get("none"):
            bits.append(f"{lad['none']} none")
        lines.append("  evidence: " + " · ".join(bits))

    waiting = [p for p in (d.get("packets") or []) if p.get("status") ==
               "presented"]
    if waiting:
        lines.append(paint("\nDECISIONS WAITING", "bold", "yellow",
                           color=color))
        for pk in waiting:
            lines.append("  • " + paint(pk.get("title", "decision"), "bold",
                                        color=color))
            for i, o in enumerate(pk.get("options", [])):
                key = chr(65 + i)
                conv = o.get("conviction", "")
                rec = " ★" if pk.get("recommendation_key") == o.get("key") \
                    else ""
                lines.append(f"      {key}) {o.get('label', '')}  "
                             f"[{conv}]  {_outcome(o, color)}{rec}")
    return "\n".join(lines)


def snapshot(overview: dict, digest: dict | None, *, color: bool = True) -> str:
    out = render_overview(overview, color=color)
    if digest is not None:
        out += "\n\n" + render_project(digest, color=color)
    return out


CLEAR = "\x1b[2J\x1b[H"   # clear screen + home cursor (for --watch)
