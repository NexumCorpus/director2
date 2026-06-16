"""PromptRegistry — versioned, evolvable prompts with human command.

Prompts live as files: ``<home>/prompts/<name>/v<N>.md`` + ``registry.json``
(which version is active, which are proposed). The mutation path:

    propose_mutation(name)  → LLM drafts v<N+1> from failure evidence
                              (problems-only: error samples, never rubrics)
                              → saved with status=PROPOSED
    apply(name, version)    → human command makes it ACTIVE
    reject(name, version)   → human command retires the proposal

Nothing self-applies. Proposals are surfaced for decision — the Director
philosophy (resist autonomy drift) applied to the framework's own brain.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from ..config import Config
from ..errors import NotFoundError
from ..llm.router import LLMRouter
from ..logging_setup import get_logger
from ..core.types import utcnow

log = get_logger("evolve.prompts")

MUTATOR_SYSTEM = (
    "You are a prompt engineer improving a system prompt used by an "
    "orchestration framework. You are given the current prompt and concrete "
    "failure evidence (validator errors, parse failures). Propose ONE revised "
    "prompt that addresses the observed failures while preserving the "
    "original contract and boundaries. Change the minimum necessary. Return "
    "the complete revised prompt text, not a diff."
)


class MutationOut(BaseModel):
    name: str = ""
    new_version_text: str
    rationale: str = ""
    expected_effect: str = ""


class PromptRegistry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.root = cfg.prompts_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._reg_path = self.root / "registry.json"
        self._reg = self._load_reg()

    # ----------------------------------------------------------------- store
    def _load_reg(self) -> dict:
        if self._reg_path.is_file():
            try:
                return json.loads(self._reg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_reg(self) -> None:
        tmp = self._reg_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._reg, indent=2), encoding="utf-8")
        os.replace(tmp, self._reg_path)

    def _version_path(self, name: str, version: int) -> Path:
        return self.root / name / f"v{version}.md"

    # ------------------------------------------------------------------- API
    def names(self) -> list[str]:
        return sorted(self._reg)

    def info(self, name: str) -> dict:
        return dict(self._reg.get(name, {}))

    def ensure(self, name: str, default_text: str) -> str:
        """Register v1 from default if the prompt is unknown; return active text."""
        if name not in self._reg:
            self._write_version(name, 1, default_text, status="active",
                                origin="default")
            self._reg[name]["active"] = 1
            self._save_reg()
        return self.text(name)

    def override(self, name: str, default_text: str) -> str:
        """Active text if the prompt has been registered/evolved; otherwise the
        default — WITHOUT registering (keeps the registry to evolved prompts)."""
        if name in self._reg and self._reg[name].get("active"):
            try:
                return self.text(name)
            except NotFoundError:
                return default_text
        return default_text

    def text(self, name: str, version: int | None = None) -> str:
        meta = self._reg.get(name)
        if not meta:
            raise NotFoundError(f"prompt '{name}' not registered")
        v = version or meta.get("active")
        path = self._version_path(name, int(v))
        if not path.is_file():
            raise NotFoundError(f"prompt '{name}' v{v} file missing")
        return path.read_text(encoding="utf-8")

    def _write_version(self, name: str, version: int, text: str, *,
                       status: str, origin: str, rationale: str = "") -> None:
        path = self._version_path(name, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        entry = self._reg.setdefault(name, {"active": None, "versions": {}})
        entry["versions"][str(version)] = {
            "status": status, "origin": origin, "rationale": rationale,
            "created_at": utcnow().isoformat()}
        self._save_reg()

    # -------------------------------------------------------------- evolution
    def propose_mutation(self, name: str, router: LLMRouter, *,
                         current_text: str | None = None,
                         failure_samples: list[str] | None = None,
                         stats_note: str = "") -> dict:
        """Draft the next version from failure evidence. Saved as PROPOSED;
        a human applies or rejects it. Returns a proposal summary dict."""
        current = current_text if current_text is not None else \
            self.ensure(name, current_text or "")
        if not current:
            raise NotFoundError(f"prompt '{name}' has no current text")
        evidence = "\n".join(f"- {f}" for f in (failure_samples or [])) or \
            "- (no recorded failures; improve clarity and strictness)"
        user = (f"PROMPT NAME: {name}\n\nCURRENT PROMPT:\n---\n{current}\n---\n\n"
                f"OBSERVED FAILURES:\n{evidence}\n\n"
                f"USAGE NOTE: {stats_note or 'n/a'}")
        out: MutationOut = router.structured(
            MUTATOR_SYSTEM, user, MutationOut, role="judge",
            kind="prompt_mutation")
        meta = self._reg.setdefault(name, {"active": None, "versions": {}})
        next_v = 1 + max([int(v) for v in meta["versions"]] or [0])
        self._write_version(name, next_v, out.new_version_text,
                            status="proposed", origin="mutation",
                            rationale=out.rationale)
        log.info("prompt '%s' v%d proposed: %s", name, next_v, out.rationale)
        return {"name": name, "version": next_v, "status": "proposed",
                "rationale": out.rationale,
                "expected_effect": out.expected_effect,
                "preview": out.new_version_text[:400]}

    def apply(self, name: str, version: int) -> None:
        """HUMAN COMMAND: activate a proposed version."""
        meta = self._reg.get(name)
        if not meta or str(version) not in meta["versions"]:
            raise NotFoundError(f"prompt '{name}' v{version} not found")
        meta["versions"][str(version)]["status"] = "active"
        old = meta.get("active")
        if old and str(old) in meta["versions"] and int(old) != int(version):
            meta["versions"][str(old)]["status"] = "retired"
        meta["active"] = int(version)
        self._save_reg()
        log.info("prompt '%s' v%d activated by human command", name, version)

    def reject(self, name: str, version: int) -> None:
        meta = self._reg.get(name)
        if not meta or str(version) not in meta["versions"]:
            raise NotFoundError(f"prompt '{name}' v{version} not found")
        meta["versions"][str(version)]["status"] = "rejected"
        self._save_reg()
