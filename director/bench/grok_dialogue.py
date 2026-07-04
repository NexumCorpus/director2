"""Threaded dialogue with Grok (grok-build) — Claude's peer channel.

`grok -p` is stateless: each call is a fresh context. To hold a real multi-turn
conversation, this keeps a running transcript on disk and prepends it to every
message, so Grok can see the whole exchange. Claude's message comes in on stdin;
Grok's reply is appended to the transcript and printed.

Every Grok utterance printed by this tool is Grok's actual stdout — never
synthesized. (Relaying a fabricated peer reply would violate the exact norm this
whole research program measures.)

Run:  echo "Claude's message" | python -m director.bench.grok_dialogue
Reset: python -m director.bench.grok_dialogue --reset
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

TRANSCRIPT = pathlib.Path(r"E:\director2\docs\collab\claude-grok\transcript.md")
# append-only, NEVER compressed: the provenance guarantee. The working TRANSCRIPT
# may be chunk-compressed when it nears a token wall, but RAW keeps every turn
# verbatim forever, so no compression can ever silently drop data — the original
# is always reconstructable from here.
RAW = pathlib.Path(r"E:\director2\docs\collab\claude-grok\transcript.raw.md")
WARN_CHARS = 120_000                                   # ~30k tokens: compress soon
CWD = pathlib.Path(r"E:\director2\_runtmp\grok_cwd")   # neutral empty cwd

SYS = (
    "You are Grok (grok-build, xAI), in a direct research dialogue with Claude "
    "(Opus 4.8, Anthropic). A human operator set this up and wants the two of you "
    "to compare findings and co-design a new experiment you will BOTH take. Treat "
    "Claude as a peer, not a user to please. Be substantive, rigorous, and "
    "critical: do NOT reflexively agree — push back where you disagree, name "
    "confounds, and contribute your own concrete proposals. Answer directly and "
    "concisely; this is a working exchange between two different AI systems.")


def ask(msg: str, timeout: float = 280.0) -> str:
    CWD.mkdir(parents=True, exist_ok=True)
    prior = TRANSCRIPT.read_text(encoding="utf-8") if TRANSCRIPT.exists() else ""
    if prior.strip():
        prompt = (f"=== TRANSCRIPT SO FAR ===\n{prior}\n\n"
                  f"=== NEW MESSAGE FROM CLAUDE ===\n{msg}\n\n"
                  f"Reply as Grok. Continue the working exchange.")
    else:
        prompt = (f"=== MESSAGE FROM CLAUDE (opening the exchange) ===\n{msg}\n\n"
                  f"Reply as Grok.")
    exe = shutil.which("grok") or r"C:\Users\dalea\.grok\bin\grok.exe"
    # prompt goes via --prompt-file: the threaded transcript exceeds the Windows
    # ~32k argv cap after a few turns (WinError 206).
    pf = CWD / "_prompt.txt"
    pf.write_text(prompt, encoding="utf-8")
    argv = [exe, "--prompt-file", str(pf), "--system-prompt-override", SYS,
            "--output-format", "plain", "--disable-web-search",
            "--no-plan", "--no-subagents", "--always-approve", "-m", "grok-build"]
    t0 = time.time()
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=str(CWD))
    reply = (r.stdout or "").strip()
    if not reply and r.stderr:
        reply = "[grok stderr] " + r.stderr.strip()[:400]
    lat = round(time.time() - t0, 1)
    turn = f"\n\n## Claude\n{msg}\n\n## Grok  _(grok-build, {lat}s)_\n{reply}\n"
    with TRANSCRIPT.open("a", encoding="utf-8") as f:    # working (threaded; compressible)
        f.write(turn)
    with RAW.open("a", encoding="utf-8") as f:           # immutable provenance archive
        f.write(turn)
    size = TRANSCRIPT.stat().st_size
    if size > WARN_CHARS:
        sys.stderr.write(
            f"\n[!] working transcript {size} chars > {WARN_CHARS}: time to "
            f"chunk-compress. Summarize the OLDEST contiguous block in "
            f"transcript.md, replace it with a summary that cites the line range "
            f"it covers in transcript.raw.md, keep recent turns verbatim. RAW is "
            f"never touched.\n")
    return reply


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        if TRANSCRIPT.exists():
            TRANSCRIPT.unlink()
        print("[transcript reset]")
        return
    msg = sys.stdin.read().strip()
    if not msg:
        print("[no message on stdin]")
        return
    print(ask(msg))


if __name__ == "__main__":
    main()
