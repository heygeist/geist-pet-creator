#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
INSTALLER="$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py"

if [[ ! -f "$INSTALLER" ]]; then
  echo "Could not find the Codex skill installer at: $INSTALLER" >&2
  echo "Install from Codex instead: Install the geist-pet-creator skill from https://github.com/motherclaw/geist-pet-creator/tree/main/geist-pet-creator" >&2
  exit 1
fi

python "$INSTALLER" --repo motherclaw/geist-pet-creator --path geist-pet-creator "$@"
