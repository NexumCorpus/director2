"""Live-generation-streaming backend + router (Phase 2). All offline:
mock backend + a canned stream-json fixture; no real CLI is ever spawned."""

import json
import subprocess

import pytest

from director.config import Config
from director.llm import claude_cli
from director.llm.base import LLMResponse
from director.llm.claude_cli import ClaudeCliBackend
from director.llm.mock import MockBackend


# ------------------------------------------------ base default stream()
def test_base_stream_default_emits_one_delta_and_returns_response():
    b = MockBackend()
    events = []
    resp = b.stream("SYS", "USER", on_event=events.append, model="",
                    temperature=0.3, max_tokens=64, timeout_s=30, kind="")
    assert isinstance(resp, LLMResponse)
    # exactly one text_delta carrying the whole completion text
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"] == resp.text
    # the non-streaming backend NEVER emits thinking_delta
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_base_stream_returns_identical_text_to_complete():
    b = MockBackend()
    kw = dict(model="", temperature=0.3, max_tokens=64, timeout_s=30,
              kind="initial_plan")
    r_complete = b.complete("SYS", "objective: x", **kw)
    r_stream = b.stream("SYS", "objective: x", on_event=lambda e: None, **kw)
    assert r_stream.text == r_complete.text
    assert r_stream.backend == r_complete.backend == "mock"
