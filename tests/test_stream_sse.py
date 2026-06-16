"""Dashboard SSE side-channel + UI pane (Phase 4). Drives the BridgeHub buffer
directly and the /stream route over loopback — no browser, no live backend."""

import json
import threading
import time
import urllib.request

import pytest

from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.dashboard.server import BridgeHub, make_server
from director.dashboard.ui import INDEX_HTML
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def hub(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    director = Director(cfg, store, router, registry, runner)
    return BridgeHub(cfg, director=director, store=store)


# ----------------------------------------------------- buffer + cursor API
def test_stream_buffer_accumulates_and_cursors(hub):
    sink = hub._make_stream_sink("p1")
    sink({"type": "text_delta", "text": "A"})
    sink({"type": "text_delta", "text": "B"})
    events, cursor = hub._stream_since("p1", 0)
    assert [e["text"] for e in events] == ["A", "B"]
    assert cursor == 2
    # incremental read from the cursor returns only the new ones
    sink({"type": "text_delta", "text": "C"})
    events2, cursor2 = hub._stream_since("p1", cursor)
    assert [e["text"] for e in events2] == ["C"] and cursor2 == 3


def test_close_stream_appends_sentinel(hub):
    hub._make_stream_sink("p2")({"type": "text_delta", "text": "x"})
    hub._close_stream("p2")
    events, _ = hub._stream_since("p2", 0)
    assert events[-1]["type"] == "done"          # terminal sentinel


def test_stream_sink_never_emits_thinking(hub):
    # truth-in-labeling: the sink path only carries the events handed to it; the
    # claude_cli backend never produces thinking_delta, so none can appear here
    sink = hub._make_stream_sink("p3")
    sink({"type": "text_delta", "text": "g"})
    events, _ = hub._stream_since("p3", 0)
    assert not any(e["type"] == "thinking_delta" for e in events)


# ------------------------------------------------------------- SSE route
@pytest.fixture()
def live(hub):
    srv = make_server(hub, port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield hub, base
    srv.shutdown()


def test_sse_route_yields_deltas_then_sentinel(live):
    hub, base = live
    # pre-seed the buffer, then close it, so the SSE drain terminates promptly
    sink = hub._make_stream_sink("proj-sse")
    sink({"type": "text_delta", "text": "hello "})
    sink({"type": "text_delta", "text": "world"})
    hub._close_stream("proj-sse")
    with urllib.request.urlopen(base + "/api/project/proj-sse/stream",
                                timeout=5) as r:
        assert r.headers.get("Content-Type", "").startswith("text/event-stream")
        body = r.read().decode("utf-8")
    # SSE framing: each event on its own `data: {json}` line, blank-line separated
    payloads = [json.loads(ln[len("data:"):].strip())
                for ln in body.splitlines() if ln.startswith("data:")]
    texts = [p["text"] for p in payloads if p.get("type") == "text_delta"]
    assert texts == ["hello ", "world"]
    assert payloads[-1]["type"] == "done"        # closed on the terminal sentinel


# ----------------------------------------------------------------- UI pane
def test_ui_has_live_generation_pane_and_eventsource():
    low = INDEX_HTML.lower()
    assert "eventsource" in low                   # opens the SSE channel
    assert "/stream" in low
    assert "live generation" in low               # the honestly-labeled pane
    # honest header: generation, NOT hidden reasoning
    assert "not hidden reasoning" in low
    # the reserved-but-dormant upgrade seam exists in the renderer
    assert "thinking_delta" in low
    # truth-in-labeling: the pane is never called "thinking"
    assert "watch it think" not in low


def test_ui_stays_offline_self_contained():
    low = INDEX_HTML.lower()
    for bad in ("http://", "https://", "cdn.", "googleapis"):
        assert bad not in low
