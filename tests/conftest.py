import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from director.config import Config  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_provider_keys(monkeypatch):
    """Tests must NEVER reach a real backend. Vars are BLANKED (not deleted):
    load_dotenv only fills variables absent from the environment, so an
    empty string also blocks re-injection from a developer's .env file —
    the leak that let two CLI tests bill real calls on 2026-06-12, and that
    later let DIRECTOR_BACKEND=claude_cli spawn real CLI processes."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                "OPENROUTER_API_KEY", "DIRECTOR_BACKEND", "DIRECTOR_MODEL",
                "DIRECTOR_CHEAP_MODEL"):
        monkeypatch.setenv(var, "")


@pytest.fixture()
def cfg(tmp_path) -> Config:
    """Isolated workspace per test."""
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    return c
