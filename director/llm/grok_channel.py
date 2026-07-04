"""Robust communications harness for Grok Build (xAI).

Supersedes the thin shell-and-strip in ``director/bench/grok_dialogue.py``. Three
robustness wins, all verified against the real CLI (2026-06-18):

1. **Native sessions.** ``grok --output-format json`` returns a ``sessionId``;
   ``grok --resume <id>`` continues that session headlessly (verified: it recalled a
   number across calls). So we send only the NEW message — Grok holds context — instead
   of replaying the whole transcript every turn (cheaper, lower-latency, no argv wall).
2. **Structured JSON.** ``{text, sessionId, stopReason, requestId, thought}`` — the
   reply is ``text`` (no stdout-strip), and we also capture Grok's ``thought`` (its
   reasoning) and ``requestId`` for provenance.
3. **Durable JSONL + fidelity.** Every turn is appended to an append-only JSONL (the
   machine-readable RAW archive); a turn is recorded as real ONLY if the call exited 0,
   the JSON parsed, and ``text`` is non-empty. stderr is NOT treated as fatal — the CLI
   emits benign ``worker quit ... AuthorizationRequired`` noise on healthy calls.

Disaster recovery: if a native ``--resume`` fails (session expired/lost), the channel
re-threads context from its own JSONL and establishes a fresh session — so native-session
efficiency never costs us the immutable-raw provenance guarantee.

Markdown ``transcript.md`` is a RENDERED VIEW of the JSONL (human/Claude-readable, and
the threading source for the recovery path); the JSONL is the source of truth.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field

_ROOT = pathlib.Path(r"E:\director2\docs\collab\grok-channels")
_BASE_FLAGS = ["--no-plan", "--no-subagents", "--always-approve",
               "--disable-web-search"]


class GrokError(Exception):
    def __init__(self, msg: str, *, transient: bool):
        super().__init__(msg)
        self.transient = transient


def _run_hardened(argv, timeout, cwd):
    """subprocess.run-like, but timeout-safe against grok's daemon.

    The grok CLI spawns/attaches a persistent leader that inherits the child's stdout
    handle. ``subprocess.run``'s timeout path kills the direct child then re-drains the
    pipe to reap it — which BLOCKS FOREVER on the leader-held handle (observed: a 260s
    call wedged for 43 min). Fix: Popen + on timeout kill the whole process TREE
    (taskkill /T reaches the leader) and do NOT re-drain. Returns (stdout, stderr, rc);
    raises subprocess.TimeoutExpired (without the blocking reap)."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", cwd=cwd)
    try:
        out, err = proc.communicate(timeout=timeout)
        return out, err, proc.returncode
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:                                              # pragma: no cover
            proc.kill()
        # deliberately NOT calling communicate() again — that is the line that hangs.
        raise


@dataclass
class Turn:
    role: str                 # 'claude' | 'grok'
    content: str
    ts: float
    session_id: str = ""
    request_id: str = ""
    stop_reason: str = ""
    thought: str = ""
    latency: float = 0.0
    ok: bool = True
    error: str = ""


@dataclass
class _State:
    name: str
    system: str = ""
    model: str = "grok-build"
    session_id: str = ""
    turns: int = 0


class GrokChannel:
    """A named, persistent, robust Grok conversation."""

    def __init__(self, name: str, *, system: str = "", model: str = "grok-build",
                 root: pathlib.Path = _ROOT, exe: str | None = None):
        self.name = name
        self.dir = root / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.dir / "turns.jsonl"          # append-only RAW (truth)
        self.transcript_md = self.dir / "transcript.md"  # rendered view
        self.state_path = self.dir / "state.json"
        self.exe = exe or shutil.which("grok") or r"C:\Users\dalea\.grok\bin\grok.exe"
        self.state = self._load_state(name, system, model)

    # --- persistence -------------------------------------------------------
    def _load_state(self, name, system, model) -> _State:
        if self.state_path.exists():
            d = json.loads(self.state_path.read_text(encoding="utf-8"))
            st = _State(**d)
            if system:                     # caller may refresh the system prompt
                st.system = system
            return st
        return _State(name=name, system=system, model=model)

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2),
                                   encoding="utf-8")

    def _append(self, turn: Turn) -> None:
        with self.jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(turn)) + "\n")

    def history(self) -> list[Turn]:
        if not self.jsonl.exists():
            return []
        out = []
        for line in self.jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Turn(**json.loads(line)))
        return out

    # --- transport ---------------------------------------------------------
    def _invoke(self, prompt: str, *, resume_id: str, set_system: bool,
                timeout: float) -> dict:
        """One grok call. Returns parsed JSON dict, or raises GrokError."""
        pf = self.dir / "_prompt.txt"
        pf.write_text(prompt, encoding="utf-8")
        argv = [self.exe, "--prompt-file", str(pf), "--output-format", "json",
                "-m", self.state.model, "--cwd", str(self.dir), *_BASE_FLAGS]
        if resume_id:
            argv += ["--resume", resume_id]
        if set_system and self.state.system:
            argv += ["--system-prompt-override", self.state.system]
        try:
            out_s, err_s, rc = _run_hardened(argv, timeout, str(self.dir))
        except subprocess.TimeoutExpired:
            raise GrokError(f"grok timed out after {timeout:.0f}s (tree killed)",
                            transient=True)
        out = (out_s or "").strip()
        if not out:
            raise GrokError(f"grok empty stdout (exit {rc}); "
                            f"stderr: {(err_s or '')[:200]}", transient=True)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            # tolerate a leading non-JSON noise line: take the last JSON object
            m = re.search(r"\{.*\}\s*$", out, re.DOTALL)
            if not m:
                raise GrokError(f"grok non-JSON stdout: {out[:200]}", transient=True)
            data = json.loads(m.group(0))
        if not str(data.get("text") or "").strip():
            raise GrokError("grok returned empty text", transient=True)
        return data

    def send(self, message: str, *, timeout: float = 280.0,
             retries: int = 2) -> Turn:
        """Send one message; return Grok's Turn. Records BOTH turns to the JSONL
        only on success (fidelity: never store a fabricated/empty reply)."""
        now = time.time()
        # record the outgoing turn immediately (it's a real fact regardless of reply)
        self._append(Turn(role="claude", content=message, ts=now,
                          session_id=self.state.session_id))

        resume_id = self.state.session_id
        set_system = not resume_id            # system set when establishing session
        prompt = message
        attempt = 0
        last_err = ""
        while True:
            t0 = time.time()
            try:
                data = self._invoke(prompt, resume_id=resume_id,
                                    set_system=set_system, timeout=timeout)
            except GrokError as e:
                last_err = str(e)
                # native resume failed -> rebuild context from JSONL, fresh session
                if resume_id and attempt == 0:
                    prompt = self._rethread(message)
                    resume_id, set_system = "", True
                    attempt += 1
                    continue
                if e.transient and attempt < retries:
                    attempt += 1
                    time.sleep(2.0 * attempt)
                    continue
                turn = Turn(role="grok", content="", ts=time.time(), ok=False,
                            error=last_err, latency=round(time.time() - t0, 1))
                self._append(turn)
                self.render()
                return turn
            lat = round(time.time() - t0, 1)
            turn = Turn(role="grok", content=data["text"].strip(), ts=time.time(),
                        session_id=data.get("sessionId", ""),
                        request_id=data.get("requestId", ""),
                        stop_reason=data.get("stopReason", ""),
                        thought=str(data.get("thought") or "")[:2000],
                        latency=lat, ok=True)
            self.state.session_id = turn.session_id or self.state.session_id
            self.state.turns += 1
            self._save_state()
            self._append(turn)
            self.render()
            return turn

    def _rethread(self, message: str) -> str:
        """Recovery: rebuild the conversation context from the JSONL when the native
        session is unavailable, so a fresh session resumes with full history."""
        parts = ["=== Prior conversation (recovered from archive) ==="]
        for t in self.history():
            if t.role == "claude":
                parts.append(f"Claude: {t.content}")
            elif t.ok and t.content:
                parts.append(f"You (Grok): {t.content}")
        parts.append("=== Continue ===")
        parts.append(f"Claude: {message}")
        return "\n\n".join(parts)

    def render(self) -> str:
        """Rebuild transcript.md from the JSONL (the human-readable view)."""
        lines = [f"# Grok channel: {self.name}",
                 f"_session {self.state.session_id or '(none)'} · "
                 f"{self.state.turns} turns · model {self.state.model}_\n"]
        for t in self.history():
            if t.role == "claude":
                lines.append(f"\n## Claude\n{t.content}")
            elif t.ok:
                tag = f"grok-build, {t.latency}s"
                lines.append(f"\n## Grok  _({tag})_\n{t.content}")
            else:
                lines.append(f"\n## Grok  _(FAILED: {t.error[:120]})_")
        md = "\n".join(lines) + "\n"
        self.transcript_md.write_text(md, encoding="utf-8")
        return md

    def ping(self, timeout: float = 60.0) -> bool:
        """Health check: a fresh (non-recorded) call that must echo a token."""
        try:
            pf = self.dir / "_ping.txt"
            pf.write_text("Reply with exactly: PONG", encoding="utf-8")
            r = subprocess.run(
                [self.exe, "--prompt-file", str(pf), "--output-format", "json",
                 "-m", self.state.model, "--cwd", str(self.dir), *_BASE_FLAGS],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, cwd=str(self.dir))
            return "PONG" in (r.stdout or "")
        except Exception:                                  # noqa: BLE001
            return False
