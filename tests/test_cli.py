"""End-to-end CLI tests on an isolated workspace, mock backend (no keys)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from director.cli import main
from director.config import Config
from director.core.state import ProjectStore


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRECTOR_HOME", str(tmp_path / "ws"))
    # provider keys AND backend selection are blanked suite-wide by the
    # autouse conftest guard; deleting any of them here would let
    # load_dotenv re-inject a developer .env (the live-billing leak)
    return tmp_path


def invoke(*args):
    runner = CliRunner()
    result = runner.invoke(main, list(args), catch_exceptions=False)
    return result


def test_init_and_doctor(env):
    r = invoke("init")
    assert r.exit_code == 0 and "workspace:" in r.output
    r2 = invoke("doctor")
    assert r2.exit_code == 0
    assert "sandbox:   ok" in r2.output


def test_full_project_arc_via_cli(env):
    r = invoke("new", "cli-demo", "-o", "build a verified toy library")
    assert r.exit_code == 0
    assert "COMMAND PACKET" in r.output

    r = invoke("status")
    assert r.exit_code == 0 and "next: director decide" in r.output

    # find the open packet id from state
    store = ProjectStore(Config.from_env())
    pid = store.get_current()
    project = store.load(pid)
    open_pkt = [p for p in project.packets.values()
                if p.status.value == "presented"][0]

    r = invoke("decide", open_pkt.id[:8], "--select",
               open_pkt.recommendation_key or "A", "-r", "test drive")
    assert r.exit_code == 0 and "decision" in r.output

    # drive to completion: decide any packets, else advance
    for _ in range(15):
        project = store.load(pid)
        open_pkts = [p for p in project.packets.values()
                     if p.status.value == "presented"]
        if open_pkts:
            invoke("decide", open_pkts[0].id[:8], "--select",
                   open_pkts[0].recommendation_key or
                   open_pkts[0].options[0].key)
            continue
        r = invoke("advance")
        assert r.exit_code == 0
        if "idle" in r.output:
            break

    project = store.load(pid)
    assert all(t.status.value in ("done", "cancelled")
               for t in project.tasks.values())

    r = invoke("finalize")
    assert r.exit_code == 0 and "[ok]" in r.output

    r = invoke("tasks", "--all")
    assert r.exit_code == 0 and "done" in r.output
    r = invoke("modules")
    assert r.exit_code == 0
    r = invoke("risks")
    assert r.exit_code == 0
    r = invoke("history", "--limit", "50")
    assert r.exit_code == 0 and "project.finalized" in r.output
    r = invoke("projects")
    assert r.exit_code == 0 and "cli-demo" in r.output


def test_memory_cli(env):
    invoke("init")
    r = invoke("memory", "remember", "the ridge blocks low sensors",
               "--tags", "isr,defense")
    assert r.exit_code == 0 and "remembered" in r.output
    r = invoke("memory", "recall", "sensor ridge blocking")
    assert r.exit_code == 0 and "ridge blocks low sensors" in r.output


def test_evolve_cli_topk(env):
    r = invoke("evolve", "domains")
    assert "topk" in r.output and "isr_placement" in r.output
    r = invoke("evolve", "run", "topk", "-n", "1")
    assert r.exit_code == 0
    assert "VERDICT:" in r.output
    r = invoke("evolve", "stats")
    assert r.exit_code == 0
    stats = json.loads(r.output[r.output.index("{"):])
    assert stats["calls"] >= 1


def test_evolve_prompt_lifecycle_cli(env):
    invoke("init")
    r = invoke("evolve", "prompts", "--propose", "role_code")
    assert r.exit_code == 0 and "PROPOSED role_code v2" in r.output
    r = invoke("evolve", "apply-prompt", "role_code", "2")
    assert r.exit_code == 0 and "now active" in r.output
    r = invoke("evolve", "prompts")
    assert "role_code: active=v2" in r.output


def test_hooks_cli(env, tmp_path):
    r = invoke("hooks", "list")
    assert "fallout2_wr" in r.output and "dmip_isr" in r.output
    out_dir = tmp_path / "pack"
    r = invoke("hooks", "scaffold", "fallout2_wr", "--out", str(out_dir))
    assert r.exit_code == 0
    assert (out_dir / "dialogue.mara.json").is_file()
    # add hook tasks to a project
    invoke("new", "modproj", "-o", "mod the wasteland")
    r = invoke("hooks", "add", "fallout2_wr")
    assert r.exit_code == 0 and "added 4 tasks" in r.output
    r = invoke("models")
    assert r.exit_code == 0 and "mock" in r.output
