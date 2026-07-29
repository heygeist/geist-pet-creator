# Geist Pet Creator

An installable Codex skill for creating, reviewing, validating, repairing, and
exporting animated Pets for [Geist](https://github.com/heygeist).

The skill keeps editable PNG frames as the source of truth, places human
approval gates in front of generated artwork, and exports the metadata and
spritesheet expected by Geist.

## What it does

- Creates a character bible and canonical base before animation work begins.
- Generates multiple candidates for each animation state and pre-screens them
  for identity, layout, transparency, and motion.
- Builds local HTML review pages with animated previews and explicit candidate
  selection.
- Validates frame counts, dimensions, alpha, safe padding, empty frames, and
  common edge artifacts.
- Repairs the smallest failing frame or state instead of regenerating an entire
  Pet.
- Exports a Geist-ready `pet.json` and lossless `spritesheet.webp`.
- Optionally installs an approved Pet into the local Geist catalog.

Generated art is never promoted into the source bundle until you approve the
exact candidate. Export and installation also happen only when requested.

## Requirements

- Codex with image generation available when creating or visibly changing art
- Python 3
- [Pillow](https://pypi.org/project/pillow/) for the bundled validation, review,
  and export scripts

Install Pillow if it is not already available:

```bash
python3 -m pip install Pillow
```

## Install

Ask Codex:

```text
Install the geist-pet-creator skill from https://github.com/heygeist/geist-pet-creator/tree/main/geist-pet-creator
```

Or clone the repository and run the helper:

```bash
git clone https://github.com/heygeist/geist-pet-creator.git
cd geist-pet-creator
./install.sh
```

The helper uses Codex's bundled skill installer. Restart Codex after installation
so the skill is discovered.

## Use

Invoke the skill explicitly and describe the Pet you want:

```text
Use $geist-pet-creator to create a Geist Pet named Rainy.
It is a small blue hooded spirit with an orange heart, a calm personality,
and soft, floaty motion. Keep the background transparent.
```

You can also use it to repair or export an existing bundle:

```text
Use $geist-pet-creator to validate and repair ./Rainy.pet.
```

```text
Use $geist-pet-creator to export ./Rainy.pet after validation passes.
```

For generated art, Codex pauses at each approval gate and shares an HTML review
page. Choose a candidate by its exact ID, for example:

```text
I choose waiting-b for waiting.
```

## Workflow

1. Define the Pet's identity, personality, visual rules, and required props.
2. Approve one canonical-base candidate.
3. Review and approve candidates for each animation state.
4. Validate the normalized `192x208` alpha PNG frames.
5. Repair any reported errors and revalidate.
6. Approve the final contact sheet, then export or install.

Each state is approved separately. A response such as “go” or “looks good” does
not select a candidate or authorize export.

## Source bundle

```text
PetName.pet/
  pet.json
  character-bible.md
  sources/
    canonical-base.png
    candidates/
    references/
    raw/
  frames/
    idle/
    running-right/
    running-left/
    waving/
    jumping/
    failed/
    waiting/
    running/
    review/
  qa/
    approvals.json
    <sprite-action>-review.html
    validation.json
  final/
    pet.json
    spritesheet.webp
```

The individual files under `frames/` are the durable source of truth. Generated
inputs, rejected attempts, and other working files stay under `sources/`.

## Bundled tools

The skill normally runs these scripts for you, but they can also be used
directly:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/geist-pet-creator"

python3 "$SKILL_DIR/scripts/validate_source_bundle.py" ./PetName.pet \
  --json-out ./PetName.pet/qa/validation.json

python3 "$SKILL_DIR/scripts/render_candidate_review_html.py" ./PetName.pet \
  --action waiting \
  --output ./PetName.pet/qa/waiting-review.html

python3 "$SKILL_DIR/scripts/export_geist_pet.py" ./PetName.pet \
  --output-dir ./PetName.pet/final
```

Pass `--install` to the export script only when you also want to install the
finished Pet into `${GEIST_HOME:-$HOME}/.geist/pets/`.

## Documentation

- [Skill instructions](geist-pet-creator/SKILL.md)
- [Source bundle contract](geist-pet-creator/references/contract.md)
- [Generation workflow](geist-pet-creator/references/generation-workflow.md)
- [QA rubric](geist-pet-creator/references/qa-rubric.md)
