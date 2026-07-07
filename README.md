# Motherclaw

Installable Codex skill bundle for creating, validating, repairing, exporting, and installing Geist Pets.

## Install

From Codex, ask:

```text
Install the geist-pet-creator skill from https://github.com/motherclaw/geist-pet-creator/tree/main/geist-pet-creator
```

Or run the bundled helper directly:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo motherclaw/geist-pet-creator \
  --path geist-pet-creator
```

Then restart Codex so the new skill is picked up.

## Use

After installing, invoke the skill in Codex:

```text
Use $geist-pet-creator to create a Geist Pet from this brief...
```

The skill enforces human approval gates for generated art, validates source bundles, exports Geist-compatible `pet.json` and `spritesheet.webp`, and can install the final Pet into a local Geist catalog when requested.
