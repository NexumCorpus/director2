"""Command Bridge server — every Director operation, one localhost page.

Routes (the SAME JSON API serves the human UI and agent operators — curl,
Claude, scripts — which is the point: dual-use by construction):

    GET  /                                  the UI (self-contained, offline)
    GET  /api                               route index (self-documenting)
    GET  /api/overview                      projects + perf + discovery runs
    GET  /api/project/<id>                  full project digest (read model)
    GET  /api/project/<id>/artifact/<aid>   artifact content
    GET  /api/project/<id>/journal?n=80     audit trail
    GET  /api/op                            background-operation state
    POST /api/new                           {name, objective}  -> background op
    POST /api/project/<id>/decide           {packet_id, option_key, rationale,
                                             modifications?, response?}
    POST /api/project/<id>/advance          {force?}      -> background op
    POST /api/project/<id>/finalize                       -> background op
    POST /api/project/<id>/approve          {task_id}

Design rules: reads come straight off the event-sourced store (no new
state); writes go ONLY through Director methods — the dashboard cannot
mutate anything the CLI couldn't. One write operation at a time: long ops
(advance/finalize) run in a background thread behind an op gate, and decide
returns 409 while one is running rather than racing the store. Binds
127.0.0.1 only.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..config import Config
from ..core.types import ResponseType, encode, utcnow
from ..errors import DirectorError, NotFoundError
from ..logging_setup import get_logger
from .ui import INDEX_HTML

log = get_logger("dashboard")

def _sv(status) -> str:
    """Status value whether it's a StrEnum (task/module/...) or a plain str
    (Project/AgentRun use bare strings)."""
    return getattr(status, "value", status)


_RESPONSE_TYPES = {
    "select": ResponseType.SELECT_OPTION,
    "select_and_modify": ResponseType.SELECT_AND_MODIFY,
    "defer": ResponseType.DEFER,
    "reject_all": ResponseType.REJECT_ALL,
    "take_command": ResponseType.TAKE_COMMAND,
}


class BridgeHub:
    """State access + the single-op write gate. Construction mirrors the CLI
    service wiring; tests inject a mock-backed Director."""

    def __init__(self, cfg: Config | None = None, *, director=None,
                 store=None, perf=None):
        self.cfg = cfg or Config.from_env()
        self.cfg.ensure_dirs()
        # the bridge makes advancing an explicit button — a decide must
        # return immediately, not drag a multi-minute agent cycle behind it
        self.cfg.auto_advance_after_decision = False
        if perf is None:
            from ..evolve.metrics import PerfLedger
            perf = PerfLedger(self.cfg)
        self.perf = perf
        if store is None:
            from ..core.state import ProjectStore
            store = ProjectStore(self.cfg)
        self.store = store
        if director is None:
            from ..agents.runner import SubAgentRunner
            from ..core.director import Director
            from ..hooks.base import (get_hook, hook_names,
                                      register_hook_verifiers)
            from ..llm.router import LLMRouter
            from ..memory.lessons import LessonLedger
            from ..verify import make_default_registry
            router = LLMRouter(self.cfg, recorder=self.perf.recorder)
            registry = make_default_registry()
            for hook_name in hook_names():
                register_hook_verifiers(registry, get_hook(hook_name))
            lessons = LessonLedger(self.cfg)
            runner = SubAgentRunner(self.cfg, router, registry,
                                    lessons_digest=lessons.digest())
            # nervous-system v2 needs the MarkerStore wired or every Credit
            # Knife / Gut Markers hook is inert (guarded by self.markers is not
            # None). Mirror the CLI service wiring: construct it only when
            # nervous_enabled (else None -> OFF byte-identical, no store touched).
            markers = None
            if self.cfg.nervous_enabled:
                from ..memory.markers import MarkerStore
                markers = MarkerStore(self.cfg)
            director = Director(self.cfg, self.store, router, registry,
                                runner, lessons=lessons, perf=self.perf,
                                markers=markers)
        self.director = director
        self._lock = threading.Lock()
        self._op = {"running": False, "kind": "", "project": "",
                    "started_at": "", "elapsed_s": 0.0,
                    "result": None, "error": ""}
        self._op_t0 = 0.0
        # live generation side-channel: per-stream-key append-only event lists,
        # guarded by _lock (mirrors the _op discipline). The cursor is just the
        # list length, so an SSE reader resumes from where it left off. Keyed by
        # project id for advance; by the op key "new" until the project id exists.
        self._streams: dict[str, list[dict]] = {}

    # -------------------------------------------------------- live generation
    def _make_stream_sink(self, key: str):
        """Return a thread-safe sink closure that appends generation events to
        ``key``'s buffer. The closure is handed to the Director plan surface and
        is called from the background advance/new-project thread; it mirrors the
        _op lock discipline. Best-effort: it never raises into the model call."""
        def sink(event: dict) -> None:
            try:
                with self._lock:
                    self._streams.setdefault(key, []).append(dict(event))
            except Exception:                                 # noqa: BLE001
                pass
        return sink

    def _close_stream(self, key: str) -> None:
        """Append the terminal sentinel so an SSE reader knows the run is done."""
        with self._lock:
            self._streams.setdefault(key, []).append({"type": "done"})

    def _stream_since(self, key: str, cursor: int) -> tuple[list[dict], int]:
        """Return (new events after ``cursor``, new cursor). Read-only over the
        buffer under the lock — the SSE loop polls this and never mutates."""
        with self._lock:
            buf = self._streams.get(key, [])
            new = buf[cursor:]
            return [dict(e) for e in new], len(buf)

    def _stream_has_sentinel(self, key: str) -> bool:
        with self._lock:
            buf = self._streams.get(key, [])
            return bool(buf) and buf[-1].get("type") == "done"

    def _reset_stream(self, key: str) -> None:
        """Clear a key's buffer at the start of a fresh op so a new run doesn't
        replay the previous run's deltas."""
        with self._lock:
            self._streams[key] = []

    # ------------------------------------------------------------------ reads
    def overview(self) -> dict:
        runs = []
        runs_dir = self.cfg.home / "runs"
        if runs_dir.is_dir():
            for d in sorted(runs_dir.iterdir(), reverse=True)[:20]:
                rj = d / "result.json"
                if rj.is_file():
                    try:
                        runs.append(json.loads(rj.read_text(encoding="utf-8")))
                    except (json.JSONDecodeError, OSError):
                        continue
        backend = getattr(getattr(self.director, "router", None),
                          "primary", "?")
        return {"projects": self.store.list_projects(),
                "current": self.store.get_current(),
                "backend": backend,
                "stats": self.perf.stats(),
                "runs": runs,
                "now": utcnow().isoformat()}

    def digest(self, pid: str) -> dict:
        p = self.store.load(pid)
        from ..core.calibration import calibration_read
        from ..core.convictions import (conviction_rank, conviction_read,
                                        evaluate_packet_coherence,
                                        honest_check)
        from ..core.taskgraph import graph_summary, milestone_blockers
        tasks = []
        for t in p.tasks.values():
            tasks.append({
                "id": t.id, "title": t.title, "role": t.role,
                "status": t.status.value, "depends_on": list(t.depends_on),
                "verifiers": list(t.verifiers),
                "artifact_ids": list(t.artifact_ids),
                "objective": (t.objective or "")[:500],
                "result_summary": (t.result_summary or "")[:400],
                "created_at": str(getattr(t, "created_at", ""))})
        milestones = []
        for m in p.milestones.values():
            milestones.append({
                "id": m.id, "name": m.name, "status": m.status.value,
                "task_ids": list(m.task_ids),
                "blockers": milestone_blockers(p, m)})
        # serialize packets, enforcing verifier honesty at the DISPLAY
        # boundary: an unbacked VERIFIED check degrades to JUDGED so the UI
        # can never paint a green check over nothing
        secret = self.cfg.report_secret()
        # verification ladder: how the LIVE decisions distribute across honest
        # tiers (the honesty model as a live readout)
        ladder = {"verified": 0, "verified_partial": 0, "judged": 0, "none": 0}
        packets = []
        for pk in p.packets.values():
            enc = encode(pk)
            presented = pk.status.value == "presented"
            for o_obj, o_enc in zip(pk.options, enc.get("options", [])):
                # display boundary: enforce the report HMAC too, so a tampered
                # persisted snapshot can't paint a partial badge over a forged
                # report (in-process provenance is already un-forgeable)
                kind, score = honest_check(o_obj, p.artifacts, secret=secret)
                o_enc["check"] = kind
                o_enc["check_score"] = score
                if presented:
                    ladder[kind] = ladder.get(kind, 0) + 1
            if presented:
                enc["coherence"] = evaluate_packet_coherence(pk, p)
            packets.append(enc)
        packets.sort(key=lambda x: (x.get("status") != "presented",
                                    x.get("created_at", "")))
        from ..core.integrity import (deliverable_partial_ok,
                                      integrity_summary, report_integrity)
        irows = report_integrity(p, secret)
        report_status = {r["artifact_id"]: r["status"] for r in irows}
        # only show a deliverable's partial badge if its backing report's
        # signature is BOUND to THIS deliverable (id + current content) — a
        # snapshot editor cannot paint a badge by setting provenance, nor replay
        # another deliverable's signed report onto this one. A property_report's
        # own integrity status rides along so the drawer can flag a tampered one.
        artifacts = [{"id": a.id, "title": a.title, "kind": a.kind,
                      "chars": len(a.content or ""),
                      "status": a.status.value,
                      "report_status": report_status.get(a.id),
                      "partial": ((a.provenance or {}).get("partial")
                                  if deliverable_partial_ok(p, a, secret)
                                  else None)}
                     for a in p.artifacts.values()]
        return {
            "id": p.id, "name": p.name, "status": _sv(p.status),
            "updated_at": str(getattr(p, "updated_at", "")),
            "charter": encode(p.charter),
            "summary": graph_summary(p),
            "conviction_read": conviction_read(p),
            "conviction_rank": conviction_rank(p),
            "conviction_calibration": calibration_read(p),
            "integrity": integrity_summary(p, secret, rows=irows),
            "ladder": ladder,
            "modules": [{"id": m.id, "name": m.name,
                         "status": m.status.value, "purpose": m.purpose}
                        for m in p.modules.values()],
            "tasks": tasks,
            "milestones": milestones,
            "packets": packets[:24],
            "decisions": [encode(d) for d in
                          list(p.decisions.values())[-12:]],
            "risks": [encode(r) for r in p.risks.values()],
            "artifacts": artifacts,
        }

    def artifact(self, pid: str, aid: str) -> dict:
        p = self.store.load(pid)
        art = p.artifacts.get(aid)
        if art is None:
            raise NotFoundError(f"no artifact {aid}")
        return {"id": art.id, "title": art.title, "kind": art.kind,
                "content": art.content or ""}

    def journal(self, pid: str, n: int = 80) -> list[dict]:
        events = [encode(e) for e in self.store.journal(pid)]
        return events[-n:]

    def integrity(self, pid: str) -> dict:
        """Per-report signature verification + the verification-health summary.
        A non-zero ``violations`` means a persisted report was tampered with."""
        from ..core.integrity import integrity_summary, report_integrity
        p = self.store.load(pid)
        secret = self.cfg.report_secret()
        return {"rows": report_integrity(p, secret),
                "summary": integrity_summary(p, secret)}

    # ----------------------------------------------------------------- writes
    def op_state(self) -> dict:
        with self._lock:
            st = dict(self._op)
            if st["running"]:
                st["elapsed_s"] = round(time.time() - self._op_t0, 1)
        return st

    def _begin(self, kind: str, project: str) -> bool:
        with self._lock:
            if self._op["running"]:
                return False
            self._op = {"running": True, "kind": kind, "project": project,
                        "started_at": utcnow().isoformat(), "elapsed_s": 0.0,
                        "result": None, "error": ""}
            self._op_t0 = time.time()
            return True

    def _finish(self, result=None, error: str = "") -> None:
        with self._lock:
            self._op.update(running=False, result=result, error=error,
                            elapsed_s=round(time.time() - self._op_t0, 1))

    def start_background(self, kind: str, pid: str, fn) -> dict:
        if not self._begin(kind, pid):
            return {"error": f"operation '{self._op['kind']}' already "
                             f"running - wait for it", "status": 409}

        def work():
            try:
                self._finish(result=fn())
            except Exception as exc:                          # noqa: BLE001
                log.exception("background %s failed", kind)
                self._finish(error=f"{type(exc).__name__}: {exc}")

        threading.Thread(target=work, daemon=True,
                         name=f"bridge-{kind}").start()
        return {"status": "started", "kind": kind, "project": pid}

    def decide(self, pid: str, body: dict) -> dict:
        with self._lock:
            if self._op["running"]:
                return {"error": f"operation '{self._op['kind']}' running - "
                                 f"decide after it completes", "status": 409}
        response = _RESPONSE_TYPES.get(str(body.get("response", "select")))
        if response is None:
            raise DirectorError(f"unknown response '{body.get('response')}'")
        if response is ResponseType.SELECT_OPTION and \
                body.get("modifications"):
            response = ResponseType.SELECT_AND_MODIFY
        return self.director.decide(
            pid, str(body.get("packet_id", "")), response=response,
            option_key=str(body.get("option_key", "")),
            rationale=str(body.get("rationale", "")),
            modifications=str(body.get("modifications", "")))


# --------------------------------------------------------------------- server
_ROUTES_DOC = [ln.strip() for ln in __doc__.splitlines()
               if ln.strip().startswith(("GET", "POST"))]


class _Handler(BaseHTTPRequestHandler):
    hub: BridgeHub = None            # injected by make_server

    def log_message(self, fmt, *args):                       # noqa: A002
        log.debug("http %s", fmt % args)

    def _send(self, code: int, payload, ctype="application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, ValueError):
            raise DirectorError("request body is not valid JSON")

    def _sse(self, pid: str) -> None:
        """Server-Sent Events drain of the live-generation buffer. The dashboard
        keys new-project generation under "new" until the project id exists, so
        accept BOTH the project id and that op key. text/event-stream, no
        Content-Length, flush per event, bounded poll loop, close on the terminal
        sentinel — so a long-lived SSE response can't starve the threaded server.
        Read-only over the buffer (the sink is the only writer)."""
        key = pid
        # the in-flight new-project op streams under "new"; route a request for
        # the still-unnamed project (or the literal 'new' key) onto it. Read
        # BOTH _streams and _op["kind"] under the SAME lock (L1) so the routing
        # decision sees a consistent snapshot.
        with self.hub._lock:
            has_pid = key in self.hub._streams
            op_is_new = self.hub._op.get("kind") == "new"
        if not has_pid and op_is_new:
            key = "new"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        # M3b: no buffer for this key AND no in-flight 'new' op to ever populate
        # one (key was NOT rerouted onto 'new') — there is nothing to read, so
        # fast-exit with a single done event instead of polling to the 600s
        # deadline. When op_is_new the key was rerouted to 'new', whose buffer
        # is populated lazily by _create, so we fall through and poll for it.
        if not has_pid and not op_is_new:
            try:
                self.wfile.write(b"data: {\"type\": \"done\"}\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        cursor = 0
        deadline = time.time() + 600          # hard cap: never hang a thread forever
        try:
            while time.time() < deadline:
                events, cursor = self.hub._stream_since(key, cursor)
                done = False
                for ev in events:
                    self.wfile.write(
                        ("data: " + json.dumps(ev, default=str)
                         + "\n\n").encode("utf-8"))
                    if ev.get("type") == "done":
                        done = True
                self.wfile.flush()
                if done:
                    break
                # no new events: if the buffer is already sentinel-terminated we
                # are finished; otherwise yield the thread briefly and re-poll
                if not events and self.hub._stream_has_sentinel(key):
                    break
                if not events:
                    time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass     # client disconnected — best-effort observability, no error

    def do_GET(self) -> None:                                # noqa: N802
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        try:
            if path == "/":
                self._send(200, INDEX_HTML.encode("utf-8"), "text/html")
            elif path == "/api":
                self._send(200, {"routes": _ROUTES_DOC})
            elif path == "/api/overview":
                self._send(200, self.hub.overview())
            elif path == "/api/op":
                self._send(200, self.hub.op_state())
            elif m := re.fullmatch(r"/api/project/([\w-]+)", path):
                self._send(200, self.hub.digest(m.group(1)))
            elif m := re.fullmatch(r"/api/project/([\w-]+)/artifact/([\w-]+)",
                                   path):
                self._send(200, self.hub.artifact(m.group(1), m.group(2)))
            elif m := re.fullmatch(r"/api/project/([\w-]+)/journal", path):
                n = int(parse_qs(url.query).get("n", ["80"])[0])
                self._send(200, self.hub.journal(m.group(1), n))
            elif m := re.fullmatch(r"/api/project/([\w-]+)/integrity", path):
                self._send(200, self.hub.integrity(m.group(1)))
            elif m := re.fullmatch(r"/api/project/([\w-]+)/stream", path):
                self._sse(m.group(1))
            else:
                self._send(404, {"error": f"no route {path}"})
        except NotFoundError as exc:
            self._send(404, {"error": str(exc)})
        except DirectorError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:                              # noqa: BLE001
            log.exception("GET %s failed", path)
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:                               # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path == "/api/new":
                body = self._body()
                name = str(body.get("name", "")).strip()
                objective = str(body.get("objective", "")).strip()
                if not name or not objective:
                    self._send(400, {"error": "name and objective required"})
                    return
                def _create():
                    # reset + sink INSIDE the op gate (M2): start_background
                    # returns 409 if a 'new' op is already running, so a 2nd
                    # concurrent create must NOT wipe the in-flight run's buffer.
                    # Only the request that actually acquires the gate touches
                    # _streams["new"].
                    self.hub._reset_stream("new")
                    sink = self.hub._make_stream_sink("new")
                    try:
                        proj, _ = self.hub.director.new_project(
                            name, objective, on_event=sink)
                        return {"project": proj.id, "name": proj.name}
                    finally:
                        self.hub._close_stream("new")

                out = self.hub.start_background("new", "", _create)
                self._send(out.pop("status", 202) if isinstance(
                    out.get("status"), int) else 202, out)
            elif m := re.fullmatch(r"/api/project/([\w-]+)/decide", path):
                out = self.hub.decide(m.group(1), self._body())
                self._send(out.pop("status", 200) if isinstance(
                    out.get("status"), int) else 200, out)
            elif m := re.fullmatch(r"/api/project/([\w-]+)/advance", path):
                body = self._body()
                pid = m.group(1)
                out = self.hub.start_background(
                    "advance", pid,
                    lambda: self.hub.director.advance(
                        pid, force=bool(body.get("force"))))
                self._send(out.pop("status", 202) if isinstance(
                    out.get("status"), int) else 202, out)
            elif m := re.fullmatch(r"/api/project/([\w-]+)/finalize", path):
                pid = m.group(1)
                out = self.hub.start_background(
                    "finalize", pid,
                    lambda: self.hub.director.finalize(pid))
                self._send(out.pop("status", 202) if isinstance(
                    out.get("status"), int) else 202, out)
            elif m := re.fullmatch(r"/api/project/([\w-]+)/approve", path):
                body = self._body()
                self._send(200, self.hub.director.approve_task(
                    m.group(1), str(body.get("task_id", ""))))
            else:
                self._send(404, {"error": f"no route {path}"})
        except NotFoundError as exc:
            self._send(404, {"error": str(exc)})
        except DirectorError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:                              # noqa: BLE001
            log.exception("POST %s failed", path)
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def make_server(hub: BridgeHub, port: int = 8765) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (_Handler,), {"hub": hub})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    return srv


def run_dashboard(port: int = 8765, open_browser: bool = False) -> None:
    hub = BridgeHub()
    srv = make_server(hub, port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    log.info("Command Bridge at %s", url)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
