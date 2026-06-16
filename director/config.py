"""Configuration: one dataclass of named, auditable knobs + a tiny .env loader.

Inherited principle from RDE: every protective mechanism is a *named* constant
here, not a magic number buried in a loop. Config is resolved once at startup:
defaults < .env file < real environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}

#: heavy single-shot LLM calls that legitimately run longer than fail-fast
#: parallel cycle calls (live finding: the finalize/synthesis call ~360s vs
#: ~150s for cycle calls). These get the LONG timeout; everything else uses the
#: base, so a stuck cycle call dies fast instead of holding a slot for minutes.
LONG_CALL_KINDS = frozenset({"agent_synthesis", "initial_plan",
                             "synthesizer_decide"})

#: LOW-STAKES calls safe to route to a faster model — ONLY command_packet, which
#: PRESENTS options for the human to choose (it doesn't decide, doesn't write the
#: deliverable, and is backstopped by trusted coherence scoring + verifier-favored
#: ★ realignment). ~26% of a live arc's wall-clock (16 calls, ~110s each).
#: DELIBERATELY EXCLUDED: adversary_attack (must be CLEVER — a dumb adversary =
#: weak hardening), prompt_mutation (quality-sensitive + rare), and every agent_*
#: deliverable/verification kind. The fast lane never touches the work product.
FAST_KINDS = frozenset({"command_packet"})


def load_dotenv(paths: list[Path] | None = None) -> None:
    """Minimal .env reader (stdlib only). Real env vars always win; .env only
    fills blanks. Searches cwd then the workspace root by default."""
    candidates = paths or [Path.cwd() / ".env", default_home() / ".env"]
    for p in candidates:
        try:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue


def default_home() -> Path:
    """Workspace root for all persistent state (projects, memory, perf, logs)."""
    env = os.environ.get("DIRECTOR_HOME")
    if env:
        return Path(env)
    return Path.home() / ".director2"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass
class Config:
    # --- workspace ----------------------------------------------------------
    home: Path = field(default_factory=default_home)

    # --- LLM transport --------------------------------------------------------
    backend: str = ""                  # "" = autodetect; anthropic|openai|xai|openrouter|mock
    model: str = ""                    # "" = backend default
    cheap_model: str = ""              # "" = backend default for low-stakes calls
    request_timeout_s: float = 120.0
    long_timeout_s: float = 0.0        # heavy single-shot calls; 0 => 3x base
    fast_model: str = ""               # model for FAST_KINDS ("" = no fast lane)
    max_retries: int = 3               # transport retries (backoff 1s, 2s, 4s)
    validation_retries: int = 1        # schema-failure retries WITH error feedback (F18 lesson)
    max_output_tokens: int = 8192      # live finding: 4096 truncated real Opus JSON
    temperature: float = 0.3

    # --- orchestration --------------------------------------------------------
    max_parallel_agents: int = 4
    max_tasks_per_advance: int = 4     # bounded auto-advance (D1.0 AdvancePolicy)
    ctx_total_chars: int = 24000       # subagent context budget (live finding:
    ctx_artifact_chars: int = 4000     # 6000-char tail-chop starved artifacts)
    auto_advance_after_decision: bool = True
    block_on_low_evaluation: bool = False
    min_evaluation_score: float = 3.0

    # --- nervous system (v1) ----------------------------------------------------
    # DEFAULT FALSE: the existing test suite stays byte-identical until ON. The
    # numbers below are deliberate first-guesses, tuned later via the bench —
    # declared here once, never hardcoded elsewhere.
    nervous_enabled: bool = False
    valence_weights: dict = field(default_factory=lambda: {
        "charter_integrity": 0.30, "accumulated_damage": 0.40,
        "uncertainty": 0.20, "resource_bleed": 0.10})   # sum to 1
    ache_threshold: float = -0.33      # composite crosses here -> ache (a wince)
    siren_threshold: float = -0.66     # composite crosses here -> siren (packet + latch)
    valence_eps: float = 0.05          # fragile band half-width around a threshold
    hysteresis_margin: float = 0.10    # clear-rule recovery margin (no flap)
    charter_breach_threshold: float = 0.90  # charter_integrity severity -> hard siren
    axis_saturation: dict = field(default_factory=lambda: {
        "accumulated_damage": 5.0, "charter_integrity": 3.0,
        "uncertainty": 4.0})           # raw signal value at which severity == 1.0
    budget: dict | None = None         # {max_cycles, max_tokens, max_wall_clock} or None -> abstain
    max_held_cycles: int = 20          # latch deadlock guard -> escalate at this hop count
    director_temperature: float | None = None  # pins director-role temperature when set
    bench: dict = field(default_factory=lambda: {
        "arms": ["on", "off"], "reps": 5, "fault_scenario": "default",
        "model_pin": "claude-sonnet-4-6", "temperature": 0.0})

    # --- sandbox / grounding ----------------------------------------------------
    sandbox_timeout_s: float = 20.0
    sandbox_mem_cap_mb: int = 1024
    bench_repeats: int = 3

    # --- improvement loop ------------------------------------------------------
    loop_iterations: int = 6
    builder_fanout: int = 1            # proposals generated CONCURRENTLY per round
    utility_eps: float = 0.01          # margin threshold for "beats" verdicts
    novelty_similarity: float = 0.85   # structural recombination threshold
    stall_window: int = 3              # rounds without improvement => stall

    # --- memory ------------------------------------------------------------------
    memory_recall_k: int = 5
    vector_dims: int = 256
    lessons_digest_max: int = 8        # bounded digest injected into prompts

    # --- logging ------------------------------------------------------------------
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        cfg = cls(
            home=default_home(),
            backend=os.environ.get("DIRECTOR_BACKEND", "").strip().lower(),
            model=os.environ.get("DIRECTOR_MODEL", "").strip(),
            cheap_model=os.environ.get("DIRECTOR_CHEAP_MODEL", "").strip(),
            request_timeout_s=_env_float("DIRECTOR_TIMEOUT_S", 120.0),
            long_timeout_s=_env_float("DIRECTOR_LONG_TIMEOUT_S", 0.0),
            fast_model=os.environ.get("DIRECTOR_FAST_MODEL", "").strip(),
            max_retries=_env_int("DIRECTOR_MAX_RETRIES", 3),
            validation_retries=_env_int("DIRECTOR_VALIDATION_RETRIES", 1),
            max_output_tokens=_env_int("DIRECTOR_MAX_OUTPUT_TOKENS", 8192),
            max_parallel_agents=_env_int("DIRECTOR_MAX_PARALLEL", 4),
            max_tasks_per_advance=_env_int("DIRECTOR_MAX_TASKS_PER_ADVANCE", 4),
            ctx_total_chars=_env_int("DIRECTOR_CTX_TOTAL_CHARS", 24000),
            ctx_artifact_chars=_env_int("DIRECTOR_CTX_ARTIFACT_CHARS", 4000),
            sandbox_timeout_s=_env_float("DIRECTOR_SANDBOX_TIMEOUT_S", 20.0),
            sandbox_mem_cap_mb=_env_int("DIRECTOR_SANDBOX_MEM_MB", 1024),
            loop_iterations=_env_int("DIRECTOR_LOOP_ITERATIONS", 6),
            builder_fanout=_env_int("DIRECTOR_BUILDER_FANOUT", 1),
            log_level=os.environ.get("DIRECTOR_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
        if os.environ.get("DIRECTOR_AUTO_ADVANCE", "").strip().lower() in _TRUTHY:
            cfg.auto_advance_after_decision = True
        elif os.environ.get("DIRECTOR_AUTO_ADVANCE", "").strip().lower() in {"0", "false", "no", "off"}:
            cfg.auto_advance_after_decision = False
        return cfg

    # --- derived paths -----------------------------------------------------------
    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def perf_dir(self) -> Path:
        return self.home / "perf"

    @property
    def prompts_dir(self) -> Path:
        return self.home / "prompts"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def runs_dir(self) -> Path:
        return self.home / "runs"

    def ensure_dirs(self) -> None:
        for p in (self.home, self.projects_dir, self.memory_dir, self.perf_dir,
                  self.prompts_dir, self.logs_dir, self.runs_dir):
            p.mkdir(parents=True, exist_ok=True)

    def kind_timeout(self, kind: str) -> float:
        """Per-kind request timeout. Heavy calls — EVERY task subagent (kind
        'agent_*'), initial planning, and synthesizer verdicts — get the long
        budget; lightweight calls (command packets, ping) use the fail-fast base.
        (Live finding: a research subagent timed out at the 360s base and cascaded
        into blocked dependents — task agents legitimately need the long lane.)"""
        if kind in LONG_CALL_KINDS or kind.startswith("agent_"):
            return self.long_timeout_s or (self.request_timeout_s * 3.0)
        return self.request_timeout_s

    def report_secret(self) -> bytes:
        """Per-workspace secret for HMAC-signing trusted reports. Kept at the
        workspace ROOT (NOT under projects/), so editing a project snapshot
        cannot reach it — a hand-forged report won't carry a valid signature.
        Created on first use."""
        path = self.home / ".report_secret"
        try:
            if path.is_file():
                return bytes.fromhex(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        secret = os.urandom(32)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secret.hex(), encoding="utf-8")
        except OSError:
            pass
        return secret

    # --- API keys -------------------------------------------------------------------
    @staticmethod
    def api_key(provider: str) -> str | None:
        env_names = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "xai": "XAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        name = env_names.get(provider)
        return os.environ.get(name) if name else None

    def detect_backend(self) -> str:
        """Explicit DIRECTOR_BACKEND wins; otherwise first provider with a key;
        otherwise mock (offline, deterministic)."""
        if self.backend:
            return self.backend
        for provider in ("anthropic", "openai", "xai", "openrouter"):
            if self.api_key(provider):
                return provider
        return "mock"
