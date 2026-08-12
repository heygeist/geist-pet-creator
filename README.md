# Geist Pet Creator

An installable Codex skill for creating, reviewing, validating, repairing, and
exporting animated Pets for [Geist](https://github.com/heygeist).

The skill keeps editable PNG frames as the source of truth, places human
approval gates in front of generated artwork, and exports the metadata and
spritesheet expected by Geist.

## What it does

- Creates a character bible, a Part Manifest, and a canonical base before
  animation work begins.
- Blends a recognizable character, cast, or mascot into the Geist house style
  when the Pet is derived from one — and builds a multi-character concept
  gallery when you want to choose from a roster.
- Generates multiple candidates for each animation state and pre-screens them
  for identity, layout, transparency, and motion.
- Draws with the agent's built-in image generation by default, or through
  OpenRouter when you configure an external image provider.
- Builds local HTML review pages with animated previews and explicit candidate
  selection.
- Validates frame counts, dimensions, alpha, safe padding, empty frames, and
  common edge artifacts.
- Audits every frame of the finished spritesheet for anatomy drift — a part
  missing, a part duplicated, or a part crossing into the next cell.
- Repairs the smallest failing frame or state instead of regenerating an entire
  Pet.
- Exports a Geist-ready `pet.json` and lossless `spritesheet.webp`.
- Optionally installs an approved Pet into the local Geist catalog.

Generated art is never promoted into the source bundle until you approve the
exact candidate. Export and installation also happen only when requested.

## Requirements

- Python 3
- [Pillow](https://pypi.org/project/pillow/) for the bundled validation, audit,
  review, and export scripts
- One way to draw, when creating or visibly changing art:
  - **Built-in image generation** — Codex's own image generation capability.
    This is the default and needs no configuration.
  - **External image provider** — an
    [OpenRouter](https://openrouter.ai) API key in `OPENROUTER_API_KEY`, plus an
    `imagegen.json` in the Pet bundle. See
    [Image generation modes](#image-generation-modes).

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

## Image generation modes

**Built-in image generation** is the default and needs no setup.

**External image provider** turns on when a Pet bundle contains `imagegen.json`:

```json
{
  "provider": "openrouter",
  "model": "google/gemini-3.1-flash-image",
  "output_format": "png",
  "background": "transparent"
}
```

`google/gemini-3.1-flash-image` is the default. Model availability drifts, so
rather than trusting a list, run the eval and pick on measured evidence:

```bash
python3 geist-pet-creator/scripts/eval_providers.py --out provider-eval --max-cost-usd 5
```

It compares each contender over three diagnostic frames on cost, duration, and
mechanical QA, then writes a review sheet for the identity judgement.

The API key comes from `OPENROUTER_API_KEY` in your environment and never enters
the bundle — the generator refuses to run if it finds a key inside
`imagegen.json`. Every run carries `--max-images` and `--max-cost-usd` ceilings,
because one call per frame across three variants and nine states is 171 requests.

Each call draws exactly one frame, with the canonical base and the previous frame
attached as references. Nothing is generated as a contact sheet, because slicing
a sheet is how part of a character ends up in the neighbouring cell.

## Identity blend

A Pet built from something already recognizable — a character, a cast, a mascot,
a known object — is neither a small copy of that source nor a plain Geist
wearing a hat. It carries two locks: the **house form** every Pet shares, and
the four to six **identity cues** that make its source nameable.

They conflict constantly, so the order is fixed:

1. House form invariants never yield — one legless rounded floating body, a
   single thick Sky outline, a Cream body area, dot eyes, a tiny mouth, exactly
   one centered Mango heart, flat fills, attached props, readable at `192x208`.
2. Identity cues yield only to the house form, and outrank every style detail.
3. Style detail yields freely.

If a style simplification would erase a recognizable feature, keep the feature
and simplify how it is drawn. If a recognizable feature would break a house-form
invariant, keep the invariant and translate the feature.

The ranked cues, their Geist translation, and the cues that were dropped go in an
`## Identity Blend` table in `character-bible.md`; countable cues also become
Part Manifest rows so the anatomy audit can count them. Every candidate is
checked against both failure directions — **franchise copy**, where the source's
style won, and **generic blob**, where the house form won — using a naming test,
a silhouette test, and a heart test, before you ever see it.

When you name a whole cast instead of one Pet, the skill generates a single
concept gallery — one mascot per cell on an invisible grid — and each cell you
pick then re-enters the normal canonical-base gate as its own sprite-scale
candidate.

The skill ships the reference images this runs on, in
[`geist-pet-creator/assets/`](geist-pet-creator/assets/README.md):
`geist-house-style.jpg` is the house form lock, attached to every derived
generation call; three galleries show the cue budget spent well; and one is a
counter-example showing the franchise-copy failure mode.

## Anatomy audit

Before a Pet can be exported, every frame is audited for **anatomy drift** — a
part of the character missing, duplicated, or crossing into the next cell.
Ordinary geometry checks cannot see these: a frame whose wing has vanished still
has the right size, the right padding, and clean alpha.

The audit measures each frame against its state's anchor frame, ranks all 57
artwork cells by suspicion, asserts the 15 unused cells are transparent, and
builds `qa/final-audit.html` — full-size frames, an animated loop per state, and
a hover overlay showing what each frame gained (red) or lost (blue).

```bash
python3 "$SKILL_DIR/scripts/audit_spritesheet.py" ./PetName.pet --repair
```

Deterministic repairs — residue, detached fragments, a body nudged back inside
safe padding — are applied in place, with a backup under
`sources/raw/repair-backups/`. Anything needing new artwork becomes a candidate
for you to approve. A frame gets at most two repair passes.

Export refuses until you approve the audit, and the approval is bound to an
`atlas_digest`, so changing a single frame reopens the gate. After export, the
written `spritesheet.webp` is audited again to catch encode damage.

## Workflow

1. Define the Pet's identity, personality, visual rules, required props, and
   Part Manifest — plus the Identity Blend, when the Pet is derived from a
   recognizable source.
2. Approve one canonical-base candidate.
3. Review and approve candidates for each animation state.
4. Validate the normalized `192x208` alpha PNG frames.
5. Repair any reported errors and revalidate.
6. Audit every frame for anatomy drift and approve the audit.
7. Export or install, then audit the exported spritesheet.

Each state is approved separately. A response such as “go” or “looks good” does
not select a candidate or authorize export.

### Part Manifest

`character-bible.md` carries the list every frame is counted against:

```markdown
## Part Manifest

| Part | Count | Side | Attachment | Notes |
| --- | --- | --- | --- | --- |
| wing | 1-2 | left, right | shoulder | one wing hides behind the body side-on |
| beak | 1 | center | face | Never duplicated |
| eye | 2 | left, right | face | Never duplicated |
```

`Count` is a number or a `min-max` range. The low bound covers poses that
legitimately hide a part; the high bound is what catches a duplicated limb.
Bundles without a manifest still audit, against the canonical base, with a
warning.

## Source bundle

```text
PetName.pet/
  pet.json
  imagegen.json            # external image provider only
  character-bible.md
  sources/
    canonical-base.png
    candidates/
    references/
      geist-house-style.png  # derived Pets
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
    final-audit.json
    final-audit.html
    repair-log.json
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

python3 "$SKILL_DIR/scripts/generate_candidates.py" ./PetName.pet \
  --state waiting --variant a --variant-intent "subtle polite lean"

python3 "$SKILL_DIR/scripts/audit_spritesheet.py" ./PetName.pet --repair

python3 "$SKILL_DIR/scripts/export_geist_pet.py" ./PetName.pet \
  --output-dir ./PetName.pet/final
```

Pass `--install` to the export script only when you also want to install the
finished Pet into `${GEIST_HOME:-$HOME}/.geist/pets/`.

`geist_grid.py`, `geist_pixels.py`, and `geist_manifest.py` sit behind those
scripts and are imported rather than run directly.

## Documentation

- [Skill instructions](geist-pet-creator/SKILL.md)
- [Source bundle contract](geist-pet-creator/references/contract.md)
- [Identity blend](geist-pet-creator/references/identity-blend.md)
- [Reference assets](geist-pet-creator/assets/README.md)
- [Generation workflow](geist-pet-creator/references/generation-workflow.md)
- [QA rubric](geist-pet-creator/references/qa-rubric.md)
- [Image generation modes](geist-pet-creator/references/image-providers.md)
