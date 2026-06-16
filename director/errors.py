"""Exception hierarchy. Every layer raises from this tree so callers can catch
at the granularity they need (e.g. ``except ModelTransientError`` to retry,
``except DirectorError`` at the CLI boundary)."""

from __future__ import annotations


class DirectorError(Exception):
    """Base for everything Director raises on purpose."""


class ConfigError(DirectorError):
    """Bad or missing configuration / API keys."""


# --- state ------------------------------------------------------------------
class StateError(DirectorError):
    """Persistence layer problems."""


class NotFoundError(StateError):
    """Entity id was not found in the store."""


class ConflictError(StateError):
    """A write would violate a uniqueness or version invariant."""


class CoherenceBlockedError(StateError):
    """A state delta failed the coherence pass and requires human judgment."""


# --- model / LLM ------------------------------------------------------------
class ModelError(DirectorError):
    """Base for all LLM-call failures."""


class ModelTransientError(ModelError):
    """Network blips, 5xx — worth retrying."""


class ModelRateLimitError(ModelTransientError):
    """429 — retry after backoff."""


class ModelParseError(ModelError):
    """Reply arrived but could not be coerced into the required JSON/schema."""


class ModelValidationError(ModelError):
    """Parsed fine but failed domain validation (e.g. empty plan)."""


class ModelProviderError(ModelError):
    """Non-transient provider rejection (bad request, auth)."""


# --- verification / execution ------------------------------------------------
class VerificationError(DirectorError):
    """A verifier chain reported a blocking failure."""


class SandboxError(DirectorError):
    """The isolated execution harness itself failed (not the candidate)."""


class SafetyViolation(DirectorError):
    """Generated code tripped the static safety screen."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations) or "unsafe code")


# --- hooks ---------------------------------------------------------------------
class HookError(DirectorError):
    """A domain hook failed to scaffold/validate."""
