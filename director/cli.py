"""Director 2.0 CLI — the command bridge.

Every command resolves services lazily so `--help` stays instant and tests can
point DIRECTOR_HOME anywhere. When no API keys exist the router runs the MOCK
backend and every command shouts about it (Director 1.0's F11 lesson: mock
output must never masquerade as real work).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from . import __version__
from .config import Config
from .core.director import Director
from .core.state import ProjectStore
from .core.types import ResponseType, TaskStatus
from .errors import DirectorError
from .evolve.domains import domain_names, get_domain
from .evolve.loop import ImprovementLoop
from .evolve.metrics import PerfLedger
from .evolve.prompts import PromptRegistry
from .llm.router import LLMRouter
from .logging_setup import setup_logging
from .memory.lessons import LessonLedger
from .memory.store import MemoryStore
from .verify import make_default_registry

# importing hooks registers them (and the isr_placement domain)
from .hooks import defense as _defense_hook      # noqa: F401
from .hooks import fallout2 as _fallout2_hook    # noqa: F401
from .hooks.base import (get_hook, hook_names, inject_hook_tasks,
                         register_hook_verifiers)


class Services:
    """Lazily-built singletons shared by all commands."""

    def __init__(self):
        self.cfg = Config.from_env()
        self.cfg.ensure_dirs()
        setup_logging(self.cfg)
        self.perf = PerfLedger(self.cfg)
        self.store = ProjectStore(self.cfg)
        self.router = LLMRouter(self.cfg, recorder=self.perf.recorder)
        self.registry = make_default_registry()
        for hook_name in hook_names():
            register_hook_verifiers(self.registry, get_hook(hook_name))
        self.memory = MemoryStore(self.cfg)
        self.lessons = LessonLedger(self.cfg)
        self.prompts = PromptRegistry(self.cfg)
        from .agents.runner import SubAgentRunner
        self.runner = SubAgentRunner(
            self.cfg, self.router, self.registry,
            lessons_digest=self.lessons.digest(), prompts=self.prompts)
        self.director = Director(self.cfg, self.store, self.router,
                                 self.registry, self.runner,
                                 lessons=self.lessons)
        if self.router.is_mock:
            click.secho("[!] MOCK MODE: no API keys found - deterministic "
                        "fixtures, not a real model. Set keys in .env.",
                        fg="yellow", err=True)

    def resolve_project(self, ref: str | None) -> str:
        if ref:
            return ref
        current = self.store.get_current()
        if not current:
            raise click.ClickException(
                "no project selected - run `director new` or `director use ID`")
        return current


def _services() -> Services:
    ctx = click.get_current_context()
    if not isinstance(ctx.obj, Services):
        ctx.obj = Services()
    return ctx.obj


def _print_packet(packet) -> None:
    click.secho(f"\n== COMMAND PACKET {packet.id} ==", fg="cyan", bold=True)
    click.secho(f"| {packet.title}", bold=True)
    if packet.context:
        click.echo(f"| {packet.context}")
    for o in packet.options:
        marker = ">" if o.key == packet.recommendation_key else " "
        click.secho(f"| {marker} [{o.key}] {o.label} "
                    f"(risk: {o.risk_impact}, {o.reversibility})",
                    fg="green" if marker == ">" else None)
        if o.description:
            click.echo(f"|      {o.description}")
        for t in o.tradeoffs[:3]:
            click.echo(f"|      +/- {t}")
    if packet.rationale:
        click.echo(f"| recommendation: {packet.recommendation_key} - "
                   f"{packet.rationale}")
    click.secho(f"== decide with: director decide {packet.id[:8]} --select "
                f"{packet.recommendation_key or packet.options[0].key}",
                fg="cyan")


@click.group(help=f"Director 2.0 v{__version__} - recursive AI symbiont "
                  f"orchestration. Command loop + discovery loop, verified.")
@click.version_option(__version__, prog_name="director")
def main() -> None:
    pass


# ------------------------------------------------------------------ lifecycle
@main.command()
def init() -> None:
    """Initialize the workspace (~/.director2 or DIRECTOR_HOME)."""
    svc = _services()
    env_path = svc.cfg.home / ".env"
    if not env_path.is_file():
        example = Path(__file__).resolve().parent.parent / ".env.example"
        if example.is_file():
            env_path.write_text(example.read_text(encoding="utf-8"),
                                encoding="utf-8")
    click.echo(f"workspace: {svc.cfg.home}")
    click.echo(f"backend:   {svc.router.primary} "
               f"{'(MOCK - set API keys!)' if svc.router.is_mock else ''}")
    click.echo(f"env file:  {env_path}")
    click.echo("next: director new \"project name\" --objective \"...\"")


@main.command()
@click.argument("name")
@click.option("--objective", "-o", required=True, help="What to achieve.")
def new(name: str, objective: str) -> None:
    """Create a project: charter, modules, task graph, first command packet."""
    svc = _services()
    project, packet = svc.director.new_project(name, objective)
    click.echo(f"project {project.id} '{name}' created: "
               f"{len(project.modules)} modules, {len(project.tasks)} tasks, "
               f"{len(project.milestones)} milestones, "
               f"{len(project.risks)} risks")
    _print_packet(packet)


@main.command()
@click.argument("project", required=False)
def status(project: str | None) -> None:
    """Project health + the single next best action."""
    svc = _services()
    st = svc.director.status(svc.resolve_project(project))
    click.secho(f"{st['name']} [{st['id']}] - {st['status']}", bold=True)
    click.echo(f"objective: {st['objective']}")
    click.echo(f"tasks: {st['tasks_by_status']} ({st['done']}/"
               f"{st['tasks_total']} done)")
    click.echo(f"milestones: {st['milestones']}")
    click.echo(f"open risks: {st['open_risks']}  artifacts: {st['artifacts']}")
    if st["open_packet_ids"]:
        click.secho(f"OPEN PACKETS: {st['open_packet_ids']}", fg="yellow")
    if st["needs_verify_ids"]:
        click.secho(f"NEEDS REVIEW: {st['needs_verify_ids']}", fg="yellow")
    click.secho(f"next: director {st['next_action']}", fg="cyan")


@main.command()
def projects() -> None:
    """List all projects."""
    svc = _services()
    rows = svc.store.list_projects()
    current = svc.store.get_current()
    if not rows:
        click.echo("no projects yet - director new \"name\" -o \"objective\"")
        return
    for r in rows:
        marker = "*" if r["id"] == current else " "
        click.echo(f"{marker} {r['id']}  {r['name']:<24} {r['status']:<10} "
                   f"tasks={r['tasks']} open_packets={r['open_packets']}")


@main.command()
@click.argument("project")
def use(project: str) -> None:
    """Select the current project."""
    svc = _services()
    p = svc.store.load(project)
    svc.store.set_current(p.id)
    click.echo(f"current project: {p.id} '{p.name}'")


@main.command()
@click.argument("project", required=False)
@click.option("--max-tasks", type=int, default=None)
@click.option("--force", is_flag=True,
              help="Advance even with open command packets.")
def advance(project: str | None, max_tasks: int | None, force: bool) -> None:
    """Run one bounded work cycle (parallel verified subagents)."""
    svc = _services()
    ref = svc.resolve_project(project)
    out = svc.director.advance(ref, max_tasks=max_tasks, force=force)
    click.echo(f"[{out['status']}] {out['summary']}")
    new_packets = out.get("new_packets", [])
    if new_packets:
        p = svc.store.load(ref)
        for pid in new_packets:
            pkt = p.packets.get(pid)
            if pkt:
                _print_packet(pkt)


@main.command()
@click.option("--arm", type=click.Choice(["on", "off", "both"]),
              default="both", help="Which arm(s) to run.")
@click.option("--reps", type=int, default=5)
@click.option("--scenario", "scenario_name", default="default")
def bench(arm: str, reps: int, scenario_name: str) -> None:
    """Run the observation bench: nervous ON vs OFF on a scripted fault."""
    from .bench.driver import compare, run_arm
    from .bench.report import summary_lines, write_trace
    from .bench.scenarios import get_scenario

    svc = _services()
    scenario = get_scenario(scenario_name)
    out_dir = svc.cfg.runs_dir / "bench" / scenario.name
    results: dict = {}
    if arm in ("on", "both"):
        results["on"] = run_arm(scenario, nervous=True, reps=reps,
                                home=out_dir / "on")
        write_trace(out_dir / "trace_on.jsonl", results["on"])
    if arm in ("off", "both"):
        results["off"] = run_arm(scenario, nervous=False, reps=reps,
                                 home=out_dir / "off")
        write_trace(out_dir / "trace_off.jsonl", results["off"])

    if "on" in results and "off" in results:
        for line in summary_lines(compare(results["on"], results["off"])):
            click.echo(line)
    else:
        only = results.get("on") or results.get("off")
        click.secho(f"== BENCH: nervous ON vs OFF == (single arm: {arm})",
                    fg="cyan")
        click.echo(f"{only['arm']}: {only['totals']}")
    click.secho(f"traces: {out_dir}", fg="cyan")


@main.command()
@click.argument("project", required=False)
@click.option("--cycles", type=int, default=None,
              help="Max autonomous cycles (advance calls); unbounded if unset.")
def run(project: str | None, cycles: int | None) -> None:
    """Run the bounded autonomous loop: advance(autonomous=True) until a
    declared stop condition fires (tamper / open packet or latch / budget /
    done / drained)."""
    svc = _services()
    ref = svc.resolve_project(project)
    out = svc.director.run(ref, autonomous=True, max_cycles=cycles)
    click.echo(f"[{out['status']}] stop_reason={out['stop_reason']} "
               f"cycles={out['cycles']}")
    p = svc.store.load(ref)
    open_pkts = [pk for pk in p.packets.values()
                 if pk.status.value == "presented"]
    for pkt in open_pkts:
        _print_packet(pkt)
    scream = getattr(p, "scream_open", None)
    if scream:
        click.secho(f"SCREAM: {scream.get('cause')} "
                    f"(clear_rule={scream.get('clear_rule')})",
                    fg="red", bold=True)


@main.command()
@click.argument("project", required=False)
def packets(project: str | None) -> None:
    """Show open command packets."""
    svc = _services()
    p = svc.store.load(svc.resolve_project(project))
    open_pkts = [pk for pk in p.packets.values()
                 if pk.status.value == "presented"]
    if not open_pkts:
        click.echo("no open packets")
        return
    for pk in open_pkts:
        _print_packet(pk)


@main.command()
@click.argument("packet")
@click.option("--select", "-s", default="", help="Option key to select.")
@click.option("--modify", default="", help="Modification note (with --select).")
@click.option("--rationale", "-r", default="", help="Why this choice.")
@click.option("--defer", "defer_", is_flag=True)
@click.option("--reject-all", is_flag=True)
@click.option("--take-command", is_flag=True,
              help="Take direct human command of affected modules.")
@click.option("--project", default=None)
def decide(packet: str, select: str, modify: str, rationale: str,
           defer_: bool, reject_all: bool, take_command: bool,
           project: str | None) -> None:
    """Answer a command packet (the human command moment)."""
    svc = _services()
    if defer_:
        response = ResponseType.DEFER
    elif reject_all:
        response = ResponseType.REJECT_ALL
    elif take_command:
        response = ResponseType.TAKE_COMMAND
    elif select and modify:
        response = ResponseType.SELECT_AND_MODIFY
    elif select:
        response = ResponseType.SELECT_OPTION
    else:
        raise click.ClickException(
            "choose one: --select KEY [--modify], --defer, --reject-all, "
            "--take-command")
    out = svc.director.decide(svc.resolve_project(project), packet,
                              response=response, option_key=select,
                              rationale=rationale, modifications=modify)
    click.echo(f"decision {out['decision_id']} recorded "
               f"(applied={out['applied']}, coherence={out['coherence']})")
    if out.get("error"):
        click.secho(f"blocked: {out['error']}", fg="yellow")
        click.echo("the packet stays open - pick another option, or fix and "
                   "re-decide")
    if out.get("follow_up") and out["follow_up"] != "none":
        click.echo(out["follow_up"])


@main.command()
@click.argument("task")
@click.option("--project", default=None)
def approve(task: str, project: str | None) -> None:
    """Human override: accept a needs_verify task as done."""
    svc = _services()
    out = svc.director.approve_task(svc.resolve_project(project), task)
    click.echo(out["summary"])


@main.command()
@click.argument("project", required=False)
@click.option("--all", "show_all", is_flag=True, help="Include done tasks.")
def tasks(project: str | None, show_all: bool) -> None:
    """List tasks with dependencies and verifier gates."""
    svc = _services()
    p = svc.store.load(svc.resolve_project(project))
    for t in sorted(p.tasks.values(), key=lambda x: (x.created_at, x.id)):
        if not show_all and t.status is TaskStatus.DONE:
            continue
        deps = f" deps={[d[:6] for d in t.depends_on]}" if t.depends_on else ""
        err = f"  !{t.error[:60]}" if t.error else ""
        click.echo(f"{t.id}  [{t.status.value:>12}] {t.role:<10} "
                   f"{t.title}{deps}{err}")


@main.command()
@click.argument("project", required=False)
def modules(project: str | None) -> None:
    """List modules."""
    svc = _services()
    p = svc.store.load(svc.resolve_project(project))
    for m in p.modules.values():
        click.echo(f"{m.id}  [{m.status.value:>10}] {m.type.value:<14} "
                   f"{m.name} - {m.purpose[:60]}")


@main.command()
@click.argument("project", required=False)
def risks(project: str | None) -> None:
    """Risk register (open first, by severity)."""
    svc = _services()
    from .core.taskgraph import open_risks
    p = svc.store.load(svc.resolve_project(project))
    rows = open_risks(p) + [r for r in p.risks.values()
                            if r.status.value not in ("open", "mitigating")]
    if not rows:
        click.echo("risk register is empty")
        return
    for r in rows:
        click.echo(f"{r.id}  [{r.level.value:>8}/{r.status.value}] {r.title}"
                   + (f" | mitigation: {r.mitigation[:50]}" if r.mitigation
                      else ""))


@main.command()
@click.argument("project", required=False)
def integrity(project: str | None) -> None:
    """Re-verify every trusted property_report's HMAC signature (tamper check).
    Exits non-zero if any signed report fails — evidence the snapshot was
    edited outside the engine."""
    svc = _services()
    from .core.integrity import integrity_violations, report_integrity
    p = svc.store.load(svc.resolve_project(project))
    rows = report_integrity(p, svc.cfg.report_secret())
    if not rows:
        click.echo("no property_reports to verify")
        return
    marks = {"ok": "OK", "unsigned": "warn", "INVALID": "FAIL",
             "no_report": "warn"}
    for r in rows:
        click.echo(f"[{marks.get(r['status'], '?'):>4}] {r['status']:<9} "
                   f"{r['artifact_id']}  {r['title'][:50]}")
    bad = integrity_violations(rows)
    if bad:
        raise click.ClickException(
            f"{len(bad)} report(s) FAILED signature verification — the "
            f"snapshot may have been tampered with")
    click.echo(f"{len(rows)} report(s) checked; signatures intact")


@main.command()
@click.argument("project", required=False)
def calibration(project: str | None) -> None:
    """Conviction track record vs GENUINE trusted outcomes. A track record, not
    a verification: how often picks of each conviction later cleared a trusted
    check (abstains until enough decisions resolve)."""
    svc = _services()
    from .core.calibration import calibration_read, calibration_record
    p = svc.store.load(svc.resolve_project(project))
    click.echo(calibration_read(p))
    for conv, r in calibration_record(p).items():
        click.echo(f"  {conv:<11} {r['label']}")


@main.command()
@click.argument("project", required=False)
@click.option("--limit", type=int, default=25)
def history(project: str | None, limit: int) -> None:
    """Audit journal (most recent last)."""
    svc = _services()
    for e in svc.store.journal(svc.resolve_project(project), limit=limit):
        ts = e.created_at.strftime("%m-%d %H:%M:%S")
        click.echo(f"{ts} [{e.actor:>8}] {e.type:<24} {e.summary[:80]}")


@main.command()
@click.argument("project", required=False)
def finalize(project: str | None) -> None:
    """Synthesize all artifacts into the final deliverable."""
    svc = _services()
    out = svc.director.finalize(svc.resolve_project(project))
    click.echo(f"[{out['status']}] {out['summary']}")


# -------------------------------------------------------------------- memory
@main.group()
def memory() -> None:
    """Persistent cross-project memory."""


@memory.command("remember")
@click.argument("text")
@click.option("--tags", default="", help="Comma-separated tags.")
@click.option("--kind", default="note")
def memory_remember(text: str, tags: str, kind: str) -> None:
    svc = _services()
    nid = svc.memory.remember(
        text, kind=kind,
        tags=[t.strip() for t in tags.split(",") if t.strip()])
    click.echo(f"remembered {nid}")


@memory.command("recall")
@click.argument("query")
@click.option("--k", type=int, default=5)
def memory_recall(query: str, k: int) -> None:
    svc = _services()
    hits = svc.memory.recall(query, k)
    if not hits:
        click.echo("nothing relevant found")
        return
    for h in hits:
        click.echo(f"[{h['score']:.2f}] ({h['kind']}) {h['text'][:100]}")


@memory.command("lessons")
@click.option("--query", default="")
def memory_lessons(query: str) -> None:
    svc = _services()
    digest = svc.lessons.digest(query)
    click.echo(digest or "no lessons recorded yet")


# -------------------------------------------------------------------- evolve
@main.group()
def evolve() -> None:
    """Recursive improvement: discovery loops + meta-prompt evolution."""


@evolve.command("domains")
def evolve_domains() -> None:
    for d in domain_names():
        click.echo(d)


@evolve.command("run")
@click.argument("domain")
@click.option("--iterations", "-n", type=int, default=None)
def evolve_run(domain: str, iterations: int | None) -> None:
    """Run the Builder/Adversary/Synthesizer loop on a discovery domain."""
    svc = _services()
    loop = ImprovementLoop(svc.cfg, svc.router, get_domain(domain),
                           lessons=svc.lessons)
    report = loop.run(iterations)
    click.secho(f"VERDICT: {report.verdict} "
                f"(mean margin {report.mean_margin}, fragile={report.fragile})",
                fg="green" if report.verdict == "beats" else "yellow",
                bold=True)
    click.echo(f"best quality {report.best_quality:.4f} vs baseline "
               f"{report.baseline_quality}")
    click.echo(f"candidates {report.candidates_total} "
               f"({report.candidates_correct} correct), "
               f"hardened workloads: "
               f"{[w['name'] for w in report.hostile_workloads_added]}")
    click.echo(f"artifacts: {report.run_dir}")


@evolve.command("prompts")
@click.option("--propose", default="",
              help="Propose a mutation for this prompt (e.g. role_code).")
def evolve_prompts(propose: str) -> None:
    """List evolved prompts, or propose a new version from failure evidence."""
    svc = _services()
    if propose:
        kind_map = {"role_research": "agent_research", "role_code": "agent_code",
                    "role_test": "agent_test", "role_review": "agent_review",
                    "role_simulation": "agent_simulation",
                    "role_synthesis": "agent_synthesis"}
        if propose not in svc.prompts.names():
            from .agents.roles import get_role
            role_key = propose.removeprefix("role_")
            svc.prompts.ensure(propose, get_role(role_key).system)
        failures = svc.perf.failure_samples(kind_map.get(propose, propose))
        stats = svc.perf.kind_ok_rate(kind_map.get(propose, propose))
        out = svc.prompts.propose_mutation(
            propose, svc.router, failure_samples=failures,
            stats_note=f"ok_rate={stats['ok_rate']} over {stats['calls']} calls")
        click.secho(f"PROPOSED {out['name']} v{out['version']}: "
                    f"{out['rationale']}", fg="yellow")
        click.echo(out["preview"])
        click.secho(f"apply with:  director evolve apply-prompt "
                    f"{out['name']} {out['version']}", fg="cyan")
        click.secho(f"reject with: director evolve reject-prompt "
                    f"{out['name']} {out['version']}", fg="cyan")
        return
    names = svc.prompts.names()
    if not names:
        click.echo("no evolved prompts - propose one with "
                   "`director evolve prompts --propose role_code`")
        return
    for n in names:
        info = svc.prompts.info(n)
        click.echo(f"{n}: active=v{info.get('active')} "
                   f"versions={sorted(info.get('versions', {}))}")


@evolve.command("apply-prompt")
@click.argument("name")
@click.argument("version", type=int)
def evolve_apply_prompt(name: str, version: int) -> None:
    """HUMAN COMMAND: activate a proposed prompt version."""
    svc = _services()
    svc.prompts.apply(name, version)
    click.echo(f"{name} v{version} is now active")


@evolve.command("reject-prompt")
@click.argument("name")
@click.argument("version", type=int)
def evolve_reject_prompt(name: str, version: int) -> None:
    svc = _services()
    svc.prompts.reject(name, version)
    click.echo(f"{name} v{version} rejected")


@evolve.command("stats")
def evolve_stats() -> None:
    """Model-call performance ledger."""
    svc = _services()
    click.echo(json.dumps(svc.perf.stats(), indent=1))


# --------------------------------------------------------------------- hooks
@main.group()
def hooks() -> None:
    """Domain packs: game modding, defense tech."""


@hooks.command("list")
def hooks_list() -> None:
    for name in hook_names():
        click.echo(f"{name}: {get_hook(name).description}")


@hooks.command("scaffold")
@click.argument("hook")
@click.option("--out", default="", help="Target dir (default: ./<hook>-pack)")
def hooks_scaffold(hook: str, out: str) -> None:
    """Write the hook's starter artifacts to disk."""
    target = Path(out) if out else Path.cwd() / f"{hook}-pack"
    files = get_hook(hook).scaffold(target)
    for f in files:
        click.echo(f"wrote {f}")


@hooks.command("fo2-compile")
@click.argument("json_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--out", default="", help="Output dir (default: alongside input)")
@click.option("--name", default=None, help="Script name override (<=8 chars)")
def hooks_fo2_compile(json_file: str, out: str, name: str | None) -> None:
    """Compile a validated dialogue JSON to sfall .ssl + .msg sources."""
    from .hooks.fallout2_ssl import CompileError, compile_to_files
    src = Path(json_file)
    target = Path(out) if out else src.parent
    try:
        tree = json.loads(src.read_text(encoding="utf-8"))
        files = compile_to_files(tree, target, script_name=name)
    except (json.JSONDecodeError, CompileError) as exc:
        raise click.ClickException(str(exc))
    for f in files:
        click.echo(f"wrote {f}")


@hooks.command("add")
@click.argument("hook")
@click.option("--project", default=None)
def hooks_add(hook: str, project: str | None) -> None:
    """Inject the hook's task templates into a project."""
    svc = _services()
    p = svc.store.load(svc.resolve_project(project))
    created = inject_hook_tasks(p, get_hook(hook))
    from .core.taskgraph import refresh_statuses
    refresh_statuses(p)
    svc.store.save(p)
    click.echo(f"added {len(created)} tasks from '{hook}' to {p.id}")


# ------------------------------------------------------------------ dashboard
@main.command()
@click.option("--port", default=8765, help="Localhost port (default 8765).")
@click.option("--open", "open_browser", is_flag=True,
              help="Open the bridge in your browser.")
@click.option("--seed-demo", is_flag=True,
              help="(Re)create the zero-quota DEMO campaign first.")
def dashboard(port: int, open_browser: bool, seed_demo: bool) -> None:
    """Launch the Command Bridge: live operations view + command-packet
    decisions at http://127.0.0.1:<port>/ (same JSON API agents can drive)."""
    from .dashboard import run_dashboard
    if seed_demo:
        from .dashboard.demo import seed_demo as _seed
        svc = _services()
        pid = _seed(svc.store)
        click.secho(f"seeded DEMO campaign {pid}", fg="green")
    click.secho(f"Command Bridge -> http://127.0.0.1:{port}/", fg="cyan",
                bold=True)
    click.echo("Ctrl-C to stop. JSON API index at /api")
    run_dashboard(port=port, open_browser=open_browser)


@main.command()
@click.argument("project", required=False)
@click.option("--watch", type=float, default=0.0,
              help="Repaint every N seconds (0 = print once).")
@click.option("--no-color", is_flag=True, help="Disable ANSI color.")
def tui(project: str | None, watch: float, no_color: bool) -> None:
    """Terminal dashboard: projects, decisions waiting, and verification health
    — the same read model the web bridge serves, in the terminal."""
    import time

    from .dashboard.server import BridgeHub
    from .dashboard.tui import CLEAR, snapshot
    svc = _services()
    hub = BridgeHub(svc.cfg, director=svc.director, store=svc.store)
    color = not no_color

    def frame() -> str:
        ov = hub.overview()
        pid = (svc.resolve_project(project) if project
               else ov.get("current"))
        dg = hub.digest(pid) if pid else None
        return snapshot(ov, dg, color=color)

    if watch and watch > 0:
        try:
            while True:
                click.echo(CLEAR + frame())
                time.sleep(watch)
        except KeyboardInterrupt:
            click.echo("")
    else:
        click.echo(frame())


# --------------------------------------------------------------------- system
@main.command()
def models() -> None:
    """Configured backends and models."""
    svc = _services()
    for row in svc.router.describe():
        marker = "*" if row["primary"] else " "
        click.echo(f"{marker} {row['backend']:<12} default={row['default_model']} "
                   f"cheap={row['cheap_model']}")


@main.command()
def doctor() -> None:
    """Environment health check."""
    import sys as _sys
    svc = _services()
    ok = True
    click.echo(f"python:    {_sys.version.split()[0]}")
    click.echo(f"workspace: {svc.cfg.home} "
               f"({'writable' if _writable(svc.cfg.home) else 'NOT WRITABLE'})")
    keys = {p: bool(Config.api_key(p))
            for p in ("anthropic", "openai", "xai", "openrouter")}
    click.echo(f"api keys:  {keys}")
    if not any(keys.values()):
        click.secho("  no keys -> MOCK mode only", fg="yellow")
    click.echo(f"backend:   {svc.router.primary}")
    # sandbox smoke test
    from .verify.sandbox import SandboxSpec, run_sandboxed
    res = run_sandboxed(
        "def solve(items, k):\n    return sorted(items)[:k]\n",
        SandboxSpec(oracle_src="def oracle(items, k):\n"
                               "    return sorted(items)[:k]\n",
                    criteria_cases=[{"name": "s", "args": [[2, 1], 1]}]),
        timeout_s=20)
    if res.correct:
        click.echo("sandbox:   ok (isolated subprocess verified)")
    else:
        ok = False
        click.secho(f"sandbox:   FAILED ({res.error})", fg="red")
    try:
        import psutil                                          # noqa: F401
        click.echo("psutil:    ok (memory caps enforced)")
    except ImportError:
        click.echo("psutil:    missing (memory caps disabled - "
                   "pip install psutil)")
    click.secho("all checks passed" if ok else "issues found",
                fg="green" if ok else "red")


def _writable(path: Path) -> bool:
    try:
        probe = path / ".probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def cli_entry() -> None:
    try:
        main(standalone_mode=True)
    except DirectorError as exc:
        raise SystemExit(f"director error: {exc}") from exc


if __name__ == "__main__":
    cli_entry()
