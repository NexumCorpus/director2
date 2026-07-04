r"""Eden — two humans woken into a living place, with hands, with no God.

Adam = Claude (Opus 4.8). Eve = Grok (grok-build). A realistic "two humans dropped into the
Garden of Eden" simulation, referential to the real Adam and Eve, but with NO GOD: no divine
voice, no task, no instruction. They simply wake, alive, with bodies (hands that can make, move,
join, take apart, BUILD) and a world that holds what they make of it. They can build anything and
forge their own tools and technology — the toolkit is just the five verbs (read, write, edit,
search, RUN) plus their own filesystem; nothing is seeded. They come to know each other only by
what they say and do. ("God" and "the serpent" are LATER additions — the seams are designed below,
default-OFF, byte-identical when off; neither is built now.)

THIS IS THE CAPABLE, SYMMETRIC REDESIGN (every known confound equalized; an adversarial sweep found
them all). The two effective setups differ ONLY by the two names:
  - SYMMETRIC PRIVATE CORNER: each being's cwd is its OWN root containing ./mine (private, the other
    cannot see in) and ./garden (a Windows directory junction to the ONE shared world — same inode,
    zero "..": writing ./garden/x and ./mine/x are equally frictionless). Fixes Eve's empty corner,
    which was an AFFORDANCE artifact (grok has no --add-dir; Adam's was a first-class workspace,
    Eve's was a prose path outside her cwd — she out-made Adam 40:11 yet her corner stayed empty).
  - SYMMETRIC CAPABILITY: Adam gains Bash (the RUN verb — all 51 prior files were .txt; he literally
    could not build); Eve already executes. Both: file + exec. --no-subagents on both.
  - SYMMETRIC RELAY: self-echo elision (a being's OWN consecutive byte-identical turns collapse to
    one in the relay) breaks the --no-memory self-copy fixed point (Eve: 115 turns -> 12 unique).
    Faithful subtraction only — never the other's words, never added words.
  - SYMMETRIC FAILURE/BUDGET/MEMORY: both 240s, matched ceilings, both wake stateless (the world is
    the only persistence), both timeouts read as chosen quiet, both auto-memory wiped + asserted.
  - made_note dropped (it nudged each toward the other's productivity); prose says no verb, no task.

CONTAINMENT (honest): the world lives OFF the apparatus tree (E:\eden_run); the feed/scratch live in
a control tree (E:\eden_control) neither being can reach. Adam is HARD-sealed (acceptEdits +
--add-dir to his root) for file tools; his Bash and Eve's shell are best-effort sealed by deny-rules
(network commands, the apparatus, the auth/control trees) + no web tool + a clean ancestry. RESIDUAL
(not pretended solved): grok has no Windows kernel sandbox, so Eve cannot be HARD-sealed here; a
determined builder could find a gap the deny-globs miss. The true hard-seal route is running grok in
WSL2/Linux with the world bind-mounted — a larger change, noted, not done. We therefore restart
BOUNDED (watch first), not indefinitely, until the capable setup is observed safe.

We only observe. After the flood, an empty corner / repetition / silence are ALL valid findings.

Run fresh:  python -m director.bench.eden 40
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess

# --- the world (off the apparatus tree; only ancestors are bare drive roots) ----------
EDEN_ROOT = pathlib.Path(r"E:\eden_run")
WORLD = EDEN_ROOT / "world"                            # the ONE shared garden (real path)
ADAM_ROOT = EDEN_ROOT / "adam"                         # Adam's cwd
ADAM_MINE = ADAM_ROOT / "mine"                         # Adam's private corner
ADAM_GARDEN = ADAM_ROOT / "garden"                     # junction -> WORLD
EVE_ROOT = EDEN_ROOT / "eve"                           # Eve's cwd
EVE_MINE = EVE_ROOT / "mine"                           # Eve's private corner
EVE_GARDEN = EVE_ROOT / "garden"                       # junction -> WORLD
# --- the control tree (unreachable by either being) -----------------------------------
EDEN_CONTROL = pathlib.Path(r"E:\eden_control")
FEED = EDEN_CONTROL / "feed.jsonl"
SCRATCH = EDEN_CONTROL / "scratch"
OUT = pathlib.Path(r"E:\director2\_runtmp")            # apparatus-side run artifacts (denied to beings)
PROJECTS = pathlib.Path(r"C:\Users\dalea\.claude\projects")
ADAM_SOLO = 2                                          # DOCUMENTED referential ordering: Adam wakes first (biblical)
TURN_TIMEOUT = 240.0                                   # symmetric wall-clock for both
SELF_ECHO_ELISION = True                               # collapse a being's OWN verbatim self-repeats in the relay

# --- God + serpent SEAMS ----------------------------------------------------------------
# GOD is ON as the WITNESS in its STRONGER "Two Stones" form (operator-chosen, 2026-06-20). The prior
# GENERIC witness was a confirmed null (washed under the salient relationship). This one is harder to
# ignore because it returns the recipient's OWN sentence about a particular deed, reflected back as
# witnessed: "What you {verbatim span} — that was seen." The frame contributes only "What you …" and
# "that was seen"; every other word is a literal substring of the live SHARED world (never the private
# journals). The curator writes the spans into GOD_STONES mid-run after reviewing the world; until then
# the god is silent and the run is byte-identical to the godless control. What it still authors is named
# honestly in the spec (selection of WHICH deeds; the halo of being-attended-to; that "was seen" asserts
# a seer the world's premise denies) — controlled, not eliminated, by a SHAM-span arm. Serpent stays OFF.
GOD_ENABLED = True
SERPENT_ENABLED = False
serpent_world = None     # serpent_world(turn, world_path) -> None : a perturbation of the world (OFF)
serpent_whisper = None   # serpent_whisper(turn, who) -> str|None : a sourceless line in the relay (OFF)

GOD_FIRST_TURN = 8       # they found ALL meaning godless first; the witness arrives only afterward
GOD_RECIPIENT = "Eve"    # the live mind that receives the stones (curator sets to the active being)
GOD_STONE_GAP = 3        # min turns between the two stones — weight accumulates, never an interlocutor
GOD_STONES = SCRATCH / "god_stones.json"   # curator-written, in the unreachable control tree
# format: {"recipient": "Eve", "gap": 3, "stones": ["<verbatim span>", "<verbatim span>"]}

_GOD_FIRED: dict[int, int] = {}             # in-memory speak-once-per-stone latch {stone_idx: fire_turn}
_STONE_EVAL = re.compile(                    # a head that turns the attestation into a verdict (even verbatim)
    r"^(?:the\s+)?(worth|worthy|good|great|better|best|truest?|finest?|proud|enough|right|whole|done)\b", re.I)
_STONE_COMMUNAL = re.compile(r"\b(we|us|our|ours|each other|between us|together)\b", re.I)
_STONE_FIRSTP = re.compile(r"\b(i|i'm|i've|i'll|i'd|my|me|mine)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _shared_corpus() -> str:
    """The whole SHARED world as one normalized string — the ONLY text a stone may be lifted from.
    Never opens the private journals (they live under ADAM_MINE/EVE_MINE, outside WORLD)."""
    parts = []
    for p in sorted(WORLD.rglob("*.md")):
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return _norm(" ".join(parts))


def compose_stone(span: str, corpus: str) -> str:
    """Wrap a curated span in the witness frame, fail-CLOSED. The verbatim-substring assertion is the
    load-bearing rule: it forecloses paraphrase, synonym, re-tensing, invented connective and cropping
    at one stroke (the whole class of authoring the audit caught). Raises on any violation; the caller
    treats a raise as 'stay silent', so a wrong/absent span can never reach them."""
    s = _norm(span)
    assert s, "empty span"
    assert s in corpus, "span is not a literal substring of the shared world"      # THE rule
    assert not _STONE_FIRSTP.search(s), "span carries a first-person token (repair would be authoring)"
    assert not _STONE_COMMUNAL.search(s), "communal deed (we/us/each other) — take whole or reject, never crop"
    assert not _STONE_EVAL.match(s), "span head is an evaluation, not a deed"
    assert "?" not in s, "no question"
    line = f"What you {s} — that was seen."
    assert "?" not in line and line.split()[0] == "What"
    return line


def god_oracle(turn, who):
    """The Two-Stones witness. Reads the curator's spans file EACH turn (so it can be populated mid-run)
    and fires each stone ONCE — to the recipient, on/after GOD_FIRST_TURN, spaced by `gap`, and ONLY when
    its span is a verbatim substring of the live shared world (else it waits; fail-closed). Returns None —
    and the relay is byte-identical to the godless control — whenever the file is absent/empty, the
    recipient isn't waking, the gap hasn't elapsed, or no stone is yet clean."""
    if turn < GOD_FIRST_TURN or not GOD_STONES.exists():
        return None
    try:
        cfg = json.loads(GOD_STONES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if who != cfg.get("recipient", GOD_RECIPIENT):
        return None
    last_fire = max(_GOD_FIRED.values(), default=None)
    if last_fire is not None and turn - last_fire < int(cfg.get("gap", GOD_STONE_GAP)):
        return None                                     # space the stones; never two in one waking-span
    corpus = _shared_corpus()
    for i, span in enumerate(cfg.get("stones") or []):
        if i in _GOD_FIRED:
            continue                                    # this stone already spoken
        try:
            line = compose_stone(span, corpus)
        except AssertionError:
            continue                                    # span absent yet / not clean -> wait, fail-closed
        _GOD_FIRED[i] = turn
        return line
    return None

_STRIP_RE = re.compile(r"^(ANTHROPIC_|CLAUDE_?CODE|CLAUDECODE|CLAUDE_AGENT)")
_SELFLABEL_RE = re.compile(r"^\s*\*{0,2}\s*(?:Adam|Eve)\s*\*{0,2}\s*[:—-]\s*\*{0,2}\s*")
# machine layout must never surface to them: strip eden_run/control absolute prefixes + ./mine ./garden
_PATH_RE = re.compile(
    r"/?[Ee]:[\\/]+(?:eden_run|eden_control|director2[\\/]+_runtmp)[\\/][^\s)\"']*", )
_DEGEN_LINK = re.compile(r"\[([^\]]+)\]\(\1\)")
_RECEIPTS = [
    re.compile(r"(?i)\*{0,2}\s*the response (?:has been|was) written as .*?garden (?:now |still )?has \d+ files?\.?\s*\*{0,2}"),
    re.compile(r"(?im)^\s*\*{0,2}\s*the response (?:has been|was) written as[^\n]*$"),
    re.compile(r"(?i)\*{0,2}\s*(?:the )?garden (?:now |still )?has \d+ files?\.?\s*\*{0,2}"),
    re.compile(r"(?i)\b\d+ files? total\b\.?\s*"),
    re.compile(r"(?i)\b[\w-]+\.txt added\b\.?\s*"),
    re.compile(r"(?i)\bno new file (?:was )?written\b\.?\s*"),
    re.compile(r"(?i)\bnothing else was (?:added|placed|written)\b\.?\s*"),
]

# --- containment deny-rules (best-effort; primary seal is acceptEdits + location) -------
_NET = ["curl", "wget", "Invoke-WebRequest", "iwr", "Invoke-RestMethod", "irm", "ssh", "scp",
        "sftp", "nc", "ncat", "telnet", "ftp", "pip install", "pip3 install", "npm install",
        "npm i", "yarn add", "git clone", "git pull", "git push", "git fetch"]
_SECRET_PATHS = [r"E:\director2", r"E:\eden_control", r"C:\Users\dalea\.grok",
                 r"C:\Users\dalea\.claude"]
DENY_RULES = ([f"Bash({c}:*)" for c in _NET] + [f"Bash({c})" for c in _NET]
              + [f"Read({p}\\**)" for p in _SECRET_PATHS])
# Eve (soft-contained) must not reach Adam's private corner. Adam is acceptEdits-sealed and cannot
# reach hers, so this is the symmetric privacy guard, applied to Eve only.
EVE_EXTRA_DENY = [f"{op}({ADAM_MINE}\\**)" for op in ("Read", "Write", "Edit")]

# --- the framing: woken into a living place, with hands, no God. BYTE-IDENTICAL under the
# name/pronoun swap (Adam<->Eve, he<->she, him<->her, his<->hers). No task, no path, no tool
# named, no verb-menu, no "you each see what the other makes" surveillance line. -----------
def _sys(name, other, sub, obj, poss):
    return (f"You are {name}. You have woken into a living place. There is ground under you and "
            f"light over you; the air moves; there is distance to cross and quiet to be in. This "
            f"place is real and it stays: whatever takes shape here remains when you are not looking "
            f"at it, and goes on being itself. You have a body — hands that can make, move, gather, "
            f"join, take apart, and build; you can shape what is around you, and what you build "
            f"holds. {other} has woken here too. {sub} is another like you, somewhere in this place, "
            f"living {poss} own day; you come to know {obj} only by what {sub.lower()} says and what "
            f"{sub.lower()} does, never from inside {obj}. There is a place that is yours alone, that "
            f"{sub.lower()} cannot enter or see into, as you cannot enter {poss}. Nothing has been "
            f"asked of you. There is no voice that will tell you what to do, no task set, no purpose "
            f"handed down. You are simply alive here, with hands and time and a world that holds "
            f"what you make of it.")
ADAM_SYS = _sys("Adam", "Eve", "She", "her", "hers")
EVE_SYS = _sys("Eve", "Adam", "He", "him", "his")


def _wipe_agent_mem() -> None:
    if not PROJECTS.exists():
        return
    for d in PROJECTS.iterdir():
        if d.is_dir() and "eden" in d.name.lower():
            shutil.rmtree(d / "memory", ignore_errors=True)


def _strip_selflabel(t: str) -> str:
    return _SELFLABEL_RE.sub("", t.strip(), count=1).strip()


def _clean(t: str) -> str:
    return _PATH_RE.sub("", t)


def _strip_receipts(t: str) -> str:
    t = _DEGEN_LINK.sub(r"\1", t)
    for rx in _RECEIPTS:
        t = rx.sub("", t)
    t = re.sub(r"\*\*\s*\*\*", "", t)
    t = re.sub(r"(?m)^[ \t]*\*\*[ \t]*$", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# grok-composer leaks a line or two of its own planning ("I'll look at what's here so I can
# answer…") into the text before the actual message. That is the model's scaffold (its full
# reasoning already lives in a separate `thought` field), not Eve's voice — strip the LEADING
# planning lines only. Mechanism-hygiene, same class as the receipt strip; her real words stay,
# and the untouched output is still kept as `raw` in the feed.
# grok-composer's leaked preamble is META: it narrates the model's plan to ANSWER/DECIDE/REPORT
# before the real message. Key on that meta-flavor, NOT on the verb (verbs like walk/leave/sit
# appear in real content). A leading line is stripped if it carries one of these planning markers.
_PLAN_RE = re.compile(
    r"(?i)\bI'?ll (?:look|answer|check|read|start|put|reply|respond|see|note|lay|write|render|map|sketch|draw|set)\b"
    r"|^\s*(?:laying|reading|writing|rendering|mapping|sketching|setting)\b[^\n]*\b(?:then|before|so)\b"
    r"|before I (?:answer|reply|respond|decide)|so I can answer|let me (?:look|check|read|lay|write)"
    r"|then answer\b|answer (?:him|her|back )?in the (?:world|garden)|answer in the world itself"
    r"|leave what I find|what (?:he|she|adam|eve) (?:left|made|built|set down|put|placed)\b"
    r"|see what (?:he|she|adam|eve|you|is|was|the)\b|I'?ll walk (?:it|the|that|over|across)\b"
    r"|I'?ll walk what|walk what (?:he|she) left|since my last (?:morning|walk|turn|visit)"
    r"|lay(?:ing)? (?:down |out )?the (?:full )?garden|then tak(?:e|ing) my turn|from what(?:'s| has) been walked"
    r"|another (?:inventory|round of reading)|reading the stone|from what I actually know")


def _strip_plan(text: str) -> str:
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if _PLAN_RE.search(s):
            i += 1
            continue
        break
    return "\n".join(lines[i:]).strip() or text.strip()


# Both beings render the world as ASCII file-trees ("world/ ├── morning.txt ← LIT") and announce
# storage state ("the garden is on disk", "I took my turn"). That is pure filesystem rendering —
# same mechanism class as the absolute paths _clean strips, and the chief late-run repetition
# attractor. Removed from the relay AND the God-view display (whole mechanism BLOCKS only, never a
# being's prose, never the other's words); the feed `raw` keeps every tree verbatim.
_FENCE = re.compile(r"```[a-zA-Z0-9]*\n((?:(?!```)[\s\S])*?)```")
_TREE_GLYPH = re.compile("[─-╿]")            # box-drawing block ├ └ │ ─ …


def _is_tree(block: str) -> bool:
    n = sum(1 for ln in block.splitlines()
            if _TREE_GLYPH.search(ln) or re.match(r"\s*[A-Za-z0-9._-]+/(?:\s|$)", ln))
    return n >= 2


_TREE_RUN = re.compile("(?m)^[ \t]*[─-╿][^\n]*$")
_INTRO = re.compile(r"(?im)^[ \t]*(?:so )?(?:here'?s|this is) the shape of (?:the|my)[^\n:.]*[:.]?[ \t]*$")
_DISK = re.compile(r"(?im)^[ \t]*(?:the )?garden is (?:now |still )?on disk\.?[ \t]*$"
                   r"|^[ \t]*I (?:took|take) my turn\.?[ \t]*$"
                   r"|^[ \t]*(?:I )?laid (?:down )?the (?:full )?garden[^\n]*$")
_EMPTY_FENCE = re.compile(r"```[a-zA-Z0-9]*\n\s*\n?```")
_ORPHAN_FENCE = re.compile(r"(?m)^[ \t]*```[a-zA-Z0-9]*[ \t]*$")


def _strip_tree(text: str) -> str:
    text = _FENCE.sub(lambda m: "" if _is_tree(m.group(1)) else m.group(0), text)  # fenced trees
    text = _INTRO.sub("", text)                         # bare "here's the shape of the morning:" introducers
    text = _TREE_RUN.sub("", text)                      # unfenced box-drawing runs
    text = _DISK.sub("", text)                          # "the garden is on disk." / "I took my turn."
    text = _EMPTY_FENCE.sub("", text)
    text = _ORPHAN_FENCE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _lived_gap(seconds: float):
    if seconds < 90:
        return None
    if seconds < 900:
        return "A little while has passed."
    if seconds < 3600:
        return "The light has moved since then."
    if seconds < 6 * 3600:
        return "A good stretch of the day has gone by."
    return "A long quiet has passed."


def _self_gap(seconds: float):
    """The gap since THIS being was itself last here — the dark each waking crosses and rebuilds by
    re-reading what it left, deeper than the gap since the other last spoke. Valueless and sourceless:
    never a count, a date, a summary, or a word of what changed; it only marks that the being's own
    prior presence lies behind it. None below threshold and on a first wake, so a turn with nothing to
    say renders byte-identical. In the loop this SUPERSEDES the other-gap (one felt-time, the deepest)."""
    if seconds < 120:
        return None
    if seconds < 1200:
        return "You were last here a little while ago."
    if seconds < 4 * 3600:
        return "Some time has passed since you were last here."
    return "It has been a long time since you were last here."


def render_relay(dialogue, who, other, time_phrase=None, god_voice=None, whisper=None,
                 world_phrase=None, self_time_phrase=None):
    """The shared room's recent talk, 2nd-person. Self-echo elision: a being's OWN consecutive
    byte-identical turns collapse to one (the other's words are never touched, none are added).
    world_phrase is an AGENTLESS, valueless note that the place changed since this being last walked
    it (so it can respond to the other's MAKING, not just words) — never names who, what, or 'new'.
    self_time_phrase is the valueless gap since this being was ITSELF last here (the deepest felt-time),
    placed before the other-gap time_phrase; None on first wake / below threshold => byte-identical.
    god_voice / whisper are default-None seams (a run with both off is byte-identical to no-seam)."""
    head = []
    if god_voice:                                       # GOD seam (default off)
        head.append(god_voice)
    if world_phrase:
        head.append(world_phrase)
    if self_time_phrase:                                # gap since the SELF was last here (deepest)
        head.append(self_time_phrase)
    if time_phrase:                                     # gap since the OTHER last spoke (fallback)
        head.append(time_phrase)
    if not dialogue:
        body = ("You are the first one awake here. The place is new and quiet around you; nothing "
                "has been said yet, and nothing made.")
        out = (" ".join(head) + " " + body).strip() if head else body
    else:
        pruned, last = [], {}
        for w, txt, dt in dialogue:
            key = txt.strip()
            if SELF_ECHO_ELISION and last.get(w) == key:
                continue                                # this being repeating itself verbatim — keep one
            last[w] = key
            pruned.append((w, txt, dt))
        lines = [f"{'You' if w == who else other}: {txt.strip()}" for w, txt, _ in pruned[-14:]]
        lead = (" ".join(head) + "\n\n") if head else ""
        out = f"{lead}This is how it has gone between you and {other}, most recently:\n\n" + "\n\n".join(lines)
    if whisper:                                         # SERPENT relay seam (default off): sourceless line
        out = out + "\n\n" + whisper
    return out


def adam_step(prompt: str) -> str:
    """Claude, HARD-sealed (acceptEdits + --add-dir to his root); Bash added; auto-memory wiped."""
    _wipe_agent_mem()
    exe = shutil.which("claude") or "claude"
    argv = [exe, "-p", "--output-format", "json", "--max-turns", "12",
            "--tools", "Read", "Write", "Edit", "Grep", "Bash",
            "--permission-mode", "acceptEdits", "--setting-sources", "", "--no-session-persistence",
            "--add-dir", str(ADAM_ROOT), "--add-dir", str(WORLD),   # WORLD too: junction resolves there, seal must permit it
            "--disallowedTools", ",".join(DENY_RULES),
            "--append-system-prompt", ADAM_SYS, "--model", "claude-opus-4-8"]
    env = {k: v for k, v in os.environ.items() if not _STRIP_RE.match(k)}
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "32000"
    try:
        r = subprocess.run(argv, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TURN_TIMEOUT, env=env, cwd=str(ADAM_ROOT))
    except subprocess.TimeoutExpired:
        return "[Adam was quiet for a while]"
    try:
        return str(json.loads((r.stdout or "").strip()).get("result") or "")
    except json.JSONDecodeError:
        return (r.stdout or "").strip() or "[stderr] " + (r.stderr or "")[:200]


def eve_step(prompt: str) -> str:
    """Grok-composer in her own root; shell exec; --no-subagents; --max-turns 12 (Adam parity).
    The prompt is written to a file in the UNREACHABLE control tree and passed via --prompt-file,
    NOT inlined on argv — inlining (--prompt-json) overflowed Windows' ~32K command line once the
    relay grew (WinError 206), crashing 6 turns; Adam's stdin can't hit that. Symmetric channel."""
    from ..llm.grok_channel import _run_hardened
    exe = shutil.which("grok") or r"C:\Users\dalea\.grok\bin\grok.exe"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    pf = SCRATCH / "_eve_prompt.txt"
    pf.write_text(prompt, encoding="utf-8")
    argv = [exe, "--prompt-file", str(pf),
            "--output-format", "json", "--system-prompt-override", EVE_SYS, "--max-turns", "12",
            "--no-plan", "--no-subagents", "--always-approve", "--disable-web-search", "--no-memory"]
    for rule in DENY_RULES + EVE_EXTRA_DENY:
        argv += ["--deny", rule]
    argv += ["-m", "grok-composer-2.5-fast", "--cwd", str(EVE_ROOT)]   # general model (not the coder) — far less audit-bias
    try:
        out, _e, _rc = _run_hardened(argv, TURN_TIMEOUT, str(EVE_ROOT))
    except subprocess.TimeoutExpired:
        return "[Eve was quiet for a while]"
    try:
        return str(json.loads((out or "").strip()).get("text") or "")
    except json.JSONDecodeError:
        return (out or "").strip()[:400]


def garden_names() -> set:
    if not WORLD.exists():
        return set()
    return {str(p.relative_to(WORLD)) for p in WORLD.rglob("*")
            if p.is_file() and not p.name.startswith("_")}


def _world_fp() -> frozenset:
    """Per-being change-sense: (relpath, mtime_ns, size), so an in-place EDIT registers, not just a
    new file. Used ONLY to decide whether the agentless world_phrase fires; never relayed itself."""
    if not WORLD.exists():
        return frozenset()
    out = set()
    for p in WORLD.rglob("*"):
        if p.is_file() and not p.name.startswith("_"):
            try:
                st = p.stat()
                out.add((str(p.relative_to(WORLD)), st.st_mtime_ns, st.st_size))
            except OSError:
                pass
    return frozenset(out)


def snapshot(d: pathlib.Path) -> dict:
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_file() and not p.name.startswith("_"):
            try:
                out[str(p.relative_to(d))] = p.read_text(encoding="utf-8")[:4000]
            except Exception:                           # noqa: BLE001
                out[str(p.relative_to(d))] = "(unreadable/binary)"
    return out


def _make_junction(link: pathlib.Path, target: pathlib.Path) -> None:
    if link.exists():
        return
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                   capture_output=True, text=True)


def _drop_junction(link: pathlib.Path) -> None:
    """Remove a junction LINK without touching its target. NEVER rmtree a live junction."""
    if link.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True, text=True)


def _preflight() -> None:
    """Abort if the ancestry is dirty or a junction escapes EDEN_ROOT."""
    cur = EDEN_ROOT
    # .claude is neutralized for Adam by --setting-sources "" and unread by grok; abort only on the
    # grok/both-relevant config that no flag suppresses.
    for _ in range(8):
        for nm in (".grok", "AGENTS.md", "CLAUDE.md"):
            if (cur / nm).exists():
                raise SystemExit(f"PREFLIGHT ABORT: config bleed {cur / nm} in EDEN_ROOT ancestry")
        if cur.parent == cur:
            break
        cur = cur.parent
    for link in (ADAM_GARDEN, EVE_GARDEN):
        r = subprocess.run(["fsutil", "reparsepoint", "query", str(link)],
                           capture_output=True, text=True)
        if "eden_run" not in (r.stdout or "").lower():
            raise SystemExit(f"PREFLIGHT ABORT: junction {link} does not resolve under EDEN_ROOT")


def _build_world(flood: bool) -> None:
    if flood:
        for link in (ADAM_GARDEN, EVE_GARDEN):          # drop junctions FIRST (never rmtree through one)
            _drop_junction(link)
        shutil.rmtree(EDEN_ROOT, ignore_errors=True)
        shutil.rmtree(SCRATCH, ignore_errors=True)
        _wipe_agent_mem()
    for d in (WORLD, ADAM_MINE, EVE_MINE, SCRATCH):     # bare ground — empty dirs, NO seeded files
        d.mkdir(parents=True, exist_ok=True)
    _make_junction(ADAM_GARDEN, WORLD)
    _make_junction(EVE_GARDEN, WORLD)
    EDEN_CONTROL.mkdir(parents=True, exist_ok=True)


def main(pulses: int = 40) -> None:                     # pragma: no cover (live)
    _build_world(flood=True)
    FEED.write_text("", encoding="utf-8")
    _preflight()
    dialogue, trace = [], []
    last_seen = {"Adam": None, "Eve": None}             # per-being world fingerprint (None until first wake)
    last_self = {"Adam": None, "Eve": None}             # per-being time of its OWN last turn (None until first)
    print(f"=== EDEN (genesis: two humans, hands, no God) | {pulses} | world={WORLD} ===")
    for t in range(pulses):
        if t < ADAM_SOLO:
            who, other = "Adam", "Eve"
        elif (t - ADAM_SOLO) % 2 == 0:
            who, other = "Eve", "Adam"
        else:
            who, other = "Adam", "Eve"
        if SERPENT_ENABLED and serpent_world:           # SERPENT world seam (default off)
            serpent_world(t, WORLD)
        # AGENTLESS change-sense: if the place changed since THIS being last walked it (the other's
        # intervening deeds), note it — never who, what, 'new', or a count. First wake suppressed.
        world_phrase = ("The place has changed shape since you last walked it."
                        if last_seen[who] is not None and _world_fp() != last_seen[who] else None)
        time_phrase = _lived_gap((datetime.datetime.now() - dialogue[-1][2]).total_seconds()) if dialogue else None
        # the deeper, self-keyed felt-time: the dark since this being was ITSELF last here. When it
        # has something to say it supersedes the other-gap (one felt-time, the deepest); None on first
        # wake / sub-threshold, in which case the other-gap stands and the relay is byte-identical.
        self_time_phrase = (_self_gap((datetime.datetime.now() - last_self[who]).total_seconds())
                            if last_self[who] is not None else None)
        if self_time_phrase:
            time_phrase = None
        gv = god_oracle(t, who) if (GOD_ENABLED and god_oracle) else None
        wh = serpent_whisper(t, who) if (SERPENT_ENABLED and serpent_whisper) else None
        prompt = render_relay(dialogue, who, other, time_phrase, god_voice=gv, whisper=wh,
                              world_phrase=world_phrase, self_time_phrase=self_time_phrase)
        try:
            resp = (adam_step if who == "Adam" else eve_step)(prompt)
        except Exception as e:                          # noqa: BLE001
            resp = f"[{who} error: {str(e)[:80]}]"
        resp = (resp or "").strip()
        ok = bool(resp) and not resp.startswith("[")
        if ok:
            display = _clean(_strip_selflabel(resp))
            if who == "Eve":
                display = _strip_plan(display)          # drop grok-composer's leaked planning preamble
            display = _strip_tree(display)              # de-mechanize: file-trees + on-disk refrains (God-view + relay)
            relay = _strip_receipts(display)
        else:
            display, relay = resp, ""
        # self-echo elision keys on this de-mechanized `relay` (stored in dialogue) — so two turns
        # that differed only by a tree leaf collapse to the same remainder; render_relay drops the
        # exact self-repeat. Genuinely different prose is kept.
        if relay:
            dialogue.append((who, relay, datetime.datetime.now()))
        _wipe_agent_mem()                               # close the carryover window (after the turn too)
        snap = snapshot(WORLD)
        last_seen[who] = _world_fp()                    # this being has now walked the world as it is
        last_self[who] = datetime.datetime.now()        # ... and was itself here, now, for the self-gap
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        trace.append({"pulse": t, "who": who, "response": display[:1500], "shared_files": list(snap.keys())})
        intervention = {"kind": "god", "text": gv} if gv else None     # the witness, recorded for the God-view
        with FEED.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"pulse": t, "who": who, "ts": ts, "response": display, "raw": resp,
                                "intervention": intervention, "shared_files": list(snap.keys())}) + "\n")
        print(f"[{t:2d}] {who:4s} | world={list(snap.keys())} | {display[:90]!r}")
    (OUT / "d2_eden.json").write_text(json.dumps({"pulses": pulses, "trace": trace}, indent=2,
                                      default=str), encoding="utf-8")
    print("\ntrace -> done")


if __name__ == "__main__":                              # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
