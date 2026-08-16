# Geist Pet Creator

An open-source Codex skill for creating, reviewing, validating, repairing, and
exporting animated Pets compatible with [Geist](https://github.com/heygeist).

The editable `192x208` alpha PNG frames remain the source of truth. The skill
adds approval gates around generated artwork, checks the full 8x9 atlas, and
exports Geist-compatible `pet.json` and lossless `spritesheet.webp` files.

> Beta: `v0.1.x` supports Codex Desktop and Codex CLI on macOS and Linux.
> Windows and other Agent Skills clients are best effort.

## Install for Codex

The easiest install is global, so the skill is available in every Codex project:

```bash
npx --yes skills@latest add heygeist/geist-pet-creator \
  --skill geist-pet-creator --agent codex --global --yes
```

Restart Codex after installation. For a project-only install, run the same
command without `--global` from that project directory.

Requirements:

- Node.js 20 or 22 for the `npx` installer
- Python 3.11, 3.12, 3.13, or 3.14
- an image-generation capability only when creating or visibly changing art

Pillow is included as a pinned dependency, but is not installed into system
Python. On first use, the skill explains the download and asks before creating
an isolated virtual environment under the user's cache. No `sudo` is used.

To inspect or manage that runtime manually:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/geist-pet-creator"
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" check
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" install
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" repair
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" remove --yes
```

Removing the runtime never removes Pet bundles or installed Pets.

## Use

Ask Codex explicitly:

```text
Use $geist-pet-creator in Quick mode to create a Geist Pet named Rainy.
It is a small blue hooded spirit with an orange heart, a calm personality,
and soft, floaty motion. Keep the background transparent.
```

Existing bundles work too:

```text
Use $geist-pet-creator to validate and repair ./Rainy.pet.
```

```text
Use $geist-pet-creator to export ./Rainy.pet after I approve the final audit.
```

### Workflow profiles

- **Quick** is the default. You choose the concept and canonical base; the agent
  promotes one candidate per animation state; you approve the final audit.
- **Studio** is opt-in. You review three candidates per animation state and
  choose each one yourself.
- **Full Automation** is explicit opt-in. The agent also chooses the canonical
  base, while the concept-sheet and final-audit human gates remain.

Installation of an exported Pet is always a separate explicit action. A broad
“go” or “continue” does not authorize spending, candidate approval, export, or
installation.

## Image generation and cost controls

Built-in image generation is the default when the running Codex client provides
it. Otherwise, the skill supports OpenRouter through `OPENROUTER_API_KEY` and a
bundle-local `imagegen.json`:

```json
{
  "provider": "openrouter",
  "model": "openai/gpt-image-2",
  "output_format": "png",
  "background": "transparent"
}
```

Before any external request, the skill gives one concise run summary: provider,
model, request count, total estimated cost when known, total cost ceiling, and
uploads. It does not itemize a per-image price. The skill then requires explicit
authority for that run ceiling. Quick mode caps a complete default generation
pass at 64 images. Every run also has hard `--max-images` and
`--max-cost-usd` limits, and failed runs can resume from the local ledger.

API keys are read only from the environment. They are rejected from Pet bundle
configuration and are not written to logs, reports, or exported files.

## Privacy

The skill is local-only and has no telemetry. Validation, repair, review pages,
and export stay on the machine. Reference images and prompts leave the machine
only when the user requests generation through the selected provider. There is
no hosted backend and no shared API key.

The `npx skills` installer is separate software downloaded from npm and is
governed by its own privacy and security terms; review it independently when
that distinction matters.

## Source bundle

```text
PetName.pet/
  pet.json
  imagegen.json             # external provider only
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
    validation.json
    final-audit.json
    final-audit.html
  final/
    pet.json
    spritesheet.webp
```

The individual files under `frames/` are durable source. Generated inputs and
rejected attempts stay under `sources/`.

## Direct tool use

After the runtime is installed:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/geist-pet-creator"
PET_PYTHON="$(python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" python)"

"$PET_PYTHON" "$SKILL_DIR/scripts/validate_source_bundle.py" ./PetName.pet \
  --json-out ./PetName.pet/qa/validation.json

"$PET_PYTHON" "$SKILL_DIR/scripts/audit_spritesheet.py" ./PetName.pet --repair

"$PET_PYTHON" "$SKILL_DIR/scripts/export_geist_pet.py" ./PetName.pet \
  --output-dir ./PetName.pet/final
```

Pass `--install` to the export command only when the user has explicitly asked
to install the finished Pet into `${GEIST_HOME:-$HOME}/.geist/pets/`.

## Project status and contribution

This repository uses semantic versions. During beta, only the latest and
previous minor line receive community support, with no response-time SLA.

- [Skill instructions](skills/geist-pet-creator/SKILL.md)
- [Source bundle contract](skills/geist-pet-creator/references/contract.md)
- [Generation workflow](skills/geist-pet-creator/references/generation-workflow.md)
- [QA rubric](skills/geist-pet-creator/references/qa-rubric.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Roadmap](ROADMAP.md)
- [Security](SECURITY.md)
- [Brand policy](BRAND.md)
- [Asset licenses](ASSET_LICENSES.md)

Code and skill instructions are licensed under MIT. Bundled artwork and the
Geist brand are governed separately. Generated output is not licensed by this
repository; users remain responsible for source and provider rights.
