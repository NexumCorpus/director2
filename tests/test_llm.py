"""LLM layer tests — all offline (httpx monkeypatched, mock backend)."""

import json

import pytest
from pydantic import BaseModel

import director.llm.base as llm_base
from director.errors import (ModelError, ModelParseError, ModelProviderError,
                             ModelValidationError)
from director.llm.anthropic import AnthropicBackend
from director.llm.base import LLMBackend, LLMResponse, ModelProfile
from director.llm.jsonx import extract_json
from director.llm.mock import MockBackend
from director.llm.openai_compat import OpenAICompatBackend
from director.llm.router import LLMRouter


# --------------------------------------------------------------------- jsonx
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "Here you go:\n```json\n{\"a\": [1, 2]}\n```\nDone."
    assert extract_json(text) == {"a": [1, 2]}


def test_extract_json_prose_wrapped():
    text = 'Sure! The answer is {"k": "v", "n": {"x": 1}} as requested.'
    assert extract_json(text) == {"k": "v", "n": {"x": 1}}


def test_extract_json_array_first():
    text = 'Result: [{"a": 1}, {"a": 2}]'
    assert extract_json(text) == [{"a": 1}, {"a": 2}]


def test_extract_json_braces_in_strings():
    text = 'prefix {"msg": "a { tricky } string"} suffix'
    assert extract_json(text) == {"msg": "a { tricky } string"}


def test_extract_json_failure():
    with pytest.raises(ValueError):
        extract_json("no json here at all")


# ----------------------------------------------------------------- transports
class _FakeResp:
    def __init__(self, status_code: int, body: dict | str):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body) if isinstance(body, dict) else body

    def json(self):
        if isinstance(self._body, dict):
            return self._body
        raise ValueError("not json")


def test_anthropic_parse(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert headers["x-api-key"] == "k"
        assert json["system"] == "sys"
        assert json["messages"][0]["content"] == "usr"
        return _FakeResp(200, {
            "type": "message", "model": "claude-test",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn"})
    monkeypatch.setattr(llm_base.httpx, "post", fake_post)
    b = AnthropicBackend(api_key="k")
    r = b.complete("sys", "usr", model="claude-test", temperature=0.1,
                   max_tokens=64, timeout_s=5)
    assert r.text == "hello" and r.prompt_tokens == 10 and r.backend == "anthropic"


def test_openai_compat_parse_and_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(429, {"error": "slow down"})
        return _FakeResp(200, {
            "model": "m", "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
    monkeypatch.setattr(llm_base.httpx, "post", fake_post)
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)
    b = OpenAICompatBackend("openrouter", base_url="https://x/v1",
                            key_env="NOPE", api_key="k", default_model="m")
    r = b.complete("s", "u", model="m", temperature=0, max_tokens=8, timeout_s=5)
    assert r.text == "ok" and calls["n"] == 2


def test_provider_error_no_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return _FakeResp(401, {"error": "bad key"})
    monkeypatch.setattr(llm_base.httpx, "post", fake_post)
    b = OpenAICompatBackend("openai", base_url="https://x/v1",
                            key_env="NOPE", api_key="bad", default_model="m")
    with pytest.raises(ModelProviderError):
        b.complete("s", "u", model="m", temperature=0, max_tokens=8, timeout_s=5)
    assert calls["n"] == 1   # 4xx is terminal, not retried


# --------------------------------------------------------------------- router
class _ScriptedBackend(LLMBackend):
    name = "scripted"
    default_model = "scripted-1"
    cheap_model = "scripted-mini"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, system, user, *, model, temperature, max_tokens,
                 timeout_s, kind=""):
        self.seen.append({"kind": kind, "user": user})
        entry = self.replies.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return LLMResponse(text=entry, model=model, backend=self.name)


class _Out(BaseModel):
    name: str
    value: int


def test_router_structured_ok(cfg):
    b = _ScriptedBackend(['{"name": "x", "value": 3}'])
    router = LLMRouter(cfg, backends={"scripted": b})
    out = router.structured("do it", "input", _Out, kind="t")
    assert out.name == "x" and out.value == 3
    # JSON contract was appended to the system prompt
    assert "OUTPUT CONTRACT" not in b.seen[0]["user"]


def test_router_structured_feedback_retry(cfg):
    b = _ScriptedBackend(['not json at all', '{"name": "y", "value": 7}'])
    router = LLMRouter(cfg, backends={"scripted": b})
    out = router.structured("do it", "input", _Out, kind="t")
    assert out.value == 7
    # second attempt carries the validator error as corrective feedback
    assert "PREVIOUS REPLY WAS REJECTED" in b.seen[1]["user"]


def test_router_structured_validation_exhausted(cfg):
    b = _ScriptedBackend(['{"name": "z"}', '{"name": "z"}'])  # missing 'value'
    router = LLMRouter(cfg, backends={"scripted": b})
    with pytest.raises((ModelValidationError, ModelParseError)):
        router.structured("do it", "input", _Out, kind="t")


def test_router_failover_real_backends(cfg, monkeypatch):
    from director.errors import ModelTransientError
    bad = _ScriptedBackend([ModelTransientError("down")])
    good = _ScriptedBackend(["fine"])
    router = LLMRouter(cfg, backends={"badone": bad, "goodone": good})
    r = router.complete("s", "u", kind="k")
    assert r.text == "fine" and r.backend == "scripted"


def test_router_never_falls_back_to_mock(cfg):
    from director.errors import ModelTransientError
    bad = _ScriptedBackend([ModelTransientError("down")])
    mock = MockBackend()
    router = LLMRouter(cfg, backends={"badone": bad, "mock": mock})
    with pytest.raises(ModelError):
        router.complete("s", "u", kind="agent_research")
    assert mock.calls == []   # mock was never consulted


def test_router_mock_primary_when_no_keys(cfg, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    router = LLMRouter(cfg)
    assert router.is_mock
    r = router.complete("s", "objective: test", kind="initial_plan")
    assert r.backend == "mock"
    assert "charter" in json.loads(r.text)


def test_router_recorder_called(cfg):
    rows = []
    b = _ScriptedBackend(["hi"])
    router = LLMRouter(cfg, backends={"scripted": b}, recorder=rows.append)
    router.complete("s", "u", kind="k", role="judge")
    assert rows and rows[0]["ok"] and rows[0]["kind"] == "k"
    assert rows[0]["role"] == "judge"


def test_mock_scriptable():
    mb = MockBackend(scripts={"weird": ['{"a": 1}']})
    r = mb.complete("s", "u", model="", temperature=0, max_tokens=8,
                    timeout_s=1, kind="weird")
    assert json.loads(r.text) == {"a": 1}


def test_profile_resolution(cfg):
    cfg.model = "my-model"
    b = _ScriptedBackend([])
    router = LLMRouter(cfg, backends={"scripted": b})
    prof = router.profile_for("director")
    assert prof.model == "my-model"
    assert b.resolve_model(prof) == "my-model"
    cheap = router.profile_for("cheap")
    assert b.resolve_model(cheap) == "scripted-mini"
