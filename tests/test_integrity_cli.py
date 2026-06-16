"""Report integrity (bound-HMAC tamper-check) + the integrity/calibration CLI."""

import json

from director.core.integrity import integrity_violations, report_integrity
from director.core.types import Artifact, Project
from director.verify.properties import run_properties
from director.verify.signing import bound_payload, content_sha, sign

SCHEMA = {"type": "object", "required": ["w"],
          "properties": {"w": {"type": "integer", "minimum": 1,
                               "maximum": 9}}}
EXAMPLE = {"w": 5}


def _report():
    return run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                          ref_independent=True)


def _bound_report_art(report, deliverable, secret):
    """A property_report whose sig is BOUND to its own id + the graded
    deliverable (id + content) — the live stamp shape."""
    r = Artifact(title="property_report", kind="property_report",
                 content=json.dumps(report),
                 provenance={"report": report, "deliverable": deliverable.id})
    r.provenance["report_sig"] = sign(
        bound_payload(report, report_id=r.id, deliverable_id=deliverable.id,
                      deliverable_sha=content_sha(deliverable.content)), secret)
    return r


def test_report_integrity_statuses():
    secret = b"z" * 32
    rep = _report()
    p = Project(name="x")
    dok = Artifact(title="dok", kind="json", content=json.dumps(EXAMPLE))
    ok = _bound_report_art(rep, dok, secret)
    dun = Artifact(title="dun", kind="json", content=json.dumps(EXAMPLE))
    unsigned = Artifact(title="property_report", kind="property_report",
                        content=json.dumps(rep),
                        provenance={"report": rep, "deliverable": dun.id})
    dtam = Artifact(title="dtam", kind="json", content=json.dumps(EXAMPLE))
    tampered = _bound_report_art(rep, dtam, secret)
    dtam.content = json.dumps({"w": 999})       # break binding after signing
    none = Artifact(title="x", kind="property_report", content="{}",
                    provenance={})
    for a in (dok, ok, dun, unsigned, dtam, tampered, none):
        p.artifacts[a.id] = a
    by_id = {r["artifact_id"]: r["status"]
             for r in report_integrity(p, secret)}
    assert by_id[ok.id] == "ok"
    assert by_id[unsigned.id] == "unsigned"
    assert by_id[tampered.id] == "INVALID"
    assert by_id[none.id] == "no_report"
    assert len(integrity_violations(report_integrity(p, secret))) == 1


def test_integrity_summary_counts(tmp_path):
    from director.config import Config
    from director.core.integrity import integrity_summary
    cfg = Config(home=tmp_path / "ws")
    cfg.ensure_dirs()
    secret = cfg.report_secret()
    p = Project(name="x")
    d = Artifact(title="d", kind="json", content=json.dumps(EXAMPLE))
    rart = _bound_report_art(_report(), d, secret)
    d.provenance = {"partial": {"n_passed": 1, "n_total": 1,
                                "report_id": rart.id}}
    p.artifacts[d.id] = d
    p.artifacts[rart.id] = rart
    s = integrity_summary(p, secret)
    assert s["reports"]["ok"] == 1
    assert s["violations"] == 0
    assert s["partial_deliverables"] == 1


def test_integrity_and_calibration_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRECTOR_HOME", str(tmp_path / "ws"))
    from click.testing import CliRunner

    from director.cli import main
    from director.config import Config
    from director.core.state import ProjectStore
    cfg = Config.from_env()
    cfg.ensure_dirs()
    store = ProjectStore(cfg)
    p = store.create("integ")
    rep = _report()
    d = Artifact(title="d", kind="json", content=json.dumps(EXAMPLE))
    a = _bound_report_art(rep, d, cfg.report_secret())
    p.artifacts[d.id] = d
    p.artifacts[a.id] = a
    store.save(p)

    runner = CliRunner()
    r = runner.invoke(main, ["integrity", p.id])
    assert r.exit_code == 0, r.output
    assert "signatures intact" in r.output

    # tamper the graded deliverable's content -> binding breaks -> non-zero exit
    d.content = json.dumps({"w": 999})
    store.save(p)
    r2 = runner.invoke(main, ["integrity", p.id])
    assert r2.exit_code != 0
    assert "FAIL" in r2.output or "tamper" in r2.output.lower()

    r3 = runner.invoke(main, ["calibration", p.id])
    assert r3.exit_code == 0, r3.output
    assert "calibration" in r3.output.lower()
