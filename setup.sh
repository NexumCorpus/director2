#!/usr/bin/env bash
# Director 2.0 — one-command setup (bash / WSL / Claude Code)
set -euo pipefail
cd "$(dirname "$0")"

echo "Director 2.0 setup"
python -m pip install -e ".[dev,mem]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env - add your API keys"
fi

director init
director doctor

echo
echo "Ready. Try:"
echo '  director new "first mission" --objective "research X and build Y"'
echo "  director evolve run topk"
