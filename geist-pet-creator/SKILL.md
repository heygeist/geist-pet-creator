---
name: geist-pet-creator
description: Create, validate, repair, and export consistent Geist-compatible Pet source bundles from approved alpha PNG frames. Use when Codex needs to make or fix a Geist Pet, Pet source bundle, character bible, generated Pet candidates, sprite-frame QA, alpha PNG cleanup, human-in-the-loop art approval, Geist pet.json metadata, spritesheet.webp export, or local Geist Pet installation.
---

# Geist Pet Creator

## Overview

Build Pets from a stable source bundle whose truth is individual alpha PNG frames, not generated strips or compressed atlases. Generated images must pass agent pre-screening and human approval before they become source frames. Export Geist-compatible `pet.json` and `spritesheet.webp` only after identity, layout, alpha, motion, and approval checks pass.

Always resolve this skill's directory first and run bundled scripts by absolute path. In examples below, set:

```bash
SKILL_DIR=/absolute/path/to/geist-pet-creator
```

## Operating Modes

- **Create**: build a new Pet source bundle from a brief, references, and approved generated candidates.
- **Repair**: fix the smallest failing unit in an existing bundle, usually one frame or one state.
- **Export/install**: validate an existing source bundle, export Geist assets, and install only when requested.

For generated or visibly changed art, stop at candidate packets until the human approves a specific option. A broad response such as "go", "continue", or "looks good" only authorizes the next generation step; it is not approval to promote generated art, normalize frames, export, or install unless the human explicitly approves the named candidate or variant. For deterministic cleanup that preserves visible art, such as clearing transparent RGB residue on already-approved frames, approval is not required.

## Core Workflow

1. Capture a Pet brief: name, personality, visual references, required props, forbidden changes, and target style.
2. Read `references/contract.md`, then write `pet.json` and `character-bible.md` before generating animation frames.
3. Generate or choose multiple canonical-base candidates as candidate packets under `sources/candidates/` using image generation for any new visible art. Pre-screen each packet, then render an HTML review page with prompts and choice controls before asking the human to choose one for `sources/canonical-base.png`.
4. For every sprite action/state, generate multiple candidate variants with image generation before producing source frames. Exception: generate and approve `running-right` first, then create `running-left` as a deterministic horizontal flip of the approved `running-right` frames unless the human explicitly requests independent left-facing art. Pre-screen every variant, render an HTML review page with prompts and choice controls, and ask the human to choose which variant to use for that action.
5. Normalize only the human-selected variant for each sprite action into `frames/<state>/<index>.png`.
6. Validate the source bundle and save machine-readable QA:

```bash
python "$SKILL_DIR/scripts/validate_source_bundle.py" /absolute/path/PetName.pet \
  --json-out /absolute/path/PetName.pet/qa/validation.json
```

7. Repair the smallest failing unit. Do not regenerate the whole Pet unless the canonical base or character bible is wrong.
8. Export only after validation passes and, when available, the human has approved the final contact sheet:

```bash
python "$SKILL_DIR/scripts/export_geist_pet.py" /absolute/path/PetName.pet \
  --output-dir /absolute/path/PetName.pet/final
```

Use `--install` only when the user wants the exported Pet installed into the local Geist catalog.

## Source Bundle

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
    idle/00.png ...
    running-right/00.png ...
    running-left/00.png ...
    waving/00.png ...
    jumping/00.png ...
    failed/00.png ...
    waiting/00.png ...
    running/00.png ...
    review/00.png ...
  qa/
    approvals.json
  final/
```

Each source frame in `frames/` must be a `192x208` RGBA PNG with transparent background and complete sprite content inside safe padding. Keep high-resolution generations, masks, strips, and rejected attempts in `sources/raw/`; normalize repaired frames into `frames/` before validation.

Required state frame counts:

| State | Frames |
| --- | ---: |
| `idle` | 6 |
| `running-right` | 8 |
| `running-left` | 8 |
| `waving` | 4 |
| `jumping` | 5 |
| `failed` | 8 |
| `waiting` | 6 |
| `running` | 6 |
| `review` | 6 |

## Human Approval Gates

- Do not promote generated art into `sources/canonical-base.png` or `frames/` until a human approves it.
- Treat the canonical base and every animation state as separate sprite actions that each need their own human validation. Required action approvals are: `canonical-base`, `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, and `review`.
- For each sprite action, provide at least 3 distinct candidate variants unless the human asks for a different count. Exception: `running-left` should normally be a single deterministic mirror candidate made from the approved `running-right` row, with its own review page and approval. Each variant must include the generated image or contact sheet, the exact prompt or deterministic operation used to create it, and a compact pre-screen summary.
- For each approval gate, create an HTML review page at `qa/<sprite-action>-review.html` using `scripts/render_candidate_review_html.py`. For animation states, the page must render each candidate as a moving sprite preview, not only as a static contact sheet. The page must also show all passing candidates, exact prompts, pre-screen summaries, a **Choose** button, and a **Copy Prompt** button for each candidate.
- Ask the human to choose one variant by candidate id before promoting that action. Do not infer approval from "go" or from approval of a different action.
- Pre-screen every candidate first. Reject obvious identity, layout, alpha, state-semantics, or prompt-compliance failures without asking the human.
- Show the human only pre-screened candidates plus a compact approval context: what was generated, the prompt used, what it must preserve, what passed, what risks remain, and the exact decision needed.
- Record approvals in `qa/approvals.json` with candidate id, approved file path, target destination, approver note, and timestamp when available.
- If the human rejects a candidate, keep the candidate packet for traceability and generate a new smallest-scope candidate.
- If the user is unavailable for approval, keep generated art in `sources/candidates/` and stop before promotion, export, or install.

## Parallel Candidate Generation

Use subagents to generate and pre-screen multiple sprite-action candidates in parallel when that would speed up a Pet build or broad repair. The main agent must create or verify the identity lock first: `pet.json`, `character-bible.md`, and `sources/canonical-base.png`.

Subagents may write candidate packets only. They must not promote frames, edit `frames/`, record final approvals, export, install, or decide which candidate won. Give each subagent a narrow action target such as `idle`, `waiting`, or `jumping`, plus the canonical base, character bible, frame count, style invariants, and destination candidate-id prefix.

Each subagent packet must include `contact-sheet.png`, `animated-preview.webp` when applicable, `prompt.md`, `inputs.json` when deterministic processing is used, `candidate-context.json`, and compact pre-screen notes. The main agent then gathers all packets, renders one combined review dashboard with animated previews, full-sheet scale/footprint comparisons, exact candidate IDs, and an approval checklist. Promote only the exact candidate IDs approved by the human after that combined review.

## Generation Rules

- Treat `character-bible.md` and `sources/canonical-base.png` as the identity lock for every frame.
- Use the built-in image generation capability (`$imagegen` / `image_gen`) for canonical-base candidates and sprite-action candidate art by default. The candidate's visible pose, expression, motion read, and frame artwork should come from generated imagery, not from scripted transforms alone.
- Every `$imagegen` call must produce a candidate packet: generated file path, exact prompt, input images, target state/frame/action, identity invariants, pre-screen result, and human-facing approval summary.
- For each sprite action, vary candidates intentionally: for example subtle, energetic, and expressive motion reads. Keep all variants inside the character bible; do not create variants by changing identity, palette, props, or style.
- Do not offer affine transforms, CSS/canvas motion, or code-distorted copies of the canonical base as final sprite-action candidates unless the human explicitly asks for deterministic prototyping. If used, label them as prototypes or archive them outside the active review set.
- Use code for processing generated art: slicing contact sheets, removing chroma-key backgrounds, alpha cleanup, resizing to `192x208`, validating frames, exporting atlases, and rendering HTML review pages.
- Prefer frame-by-frame or small state batches over whole-row strips. Never accept identity drift just because atlas geometry validates.
- Directional movement states are not literal leg-running. `running-right` must read as moving/gliding right. `running-left` must normally be the same sprite cycle as `running-right` with each approved frame horizontally flipped, not independently regenerated. Use lateral movement, drift, glide, lean, translation, soft squash/stretch, or trailing side/body shapes. Do not prompt for or accept legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics.
- `running` means active task work, not foot-running.
- Avoid detached effects, shadows, glows, motion trails, guide marks, white backgrounds, and chroma-key residue.
- Use true alpha PNGs. Chroma-key extraction is a fallback, and desaturated edge cleanup must happen before a frame enters `frames/`.

## Validation And Repair

- Treat `qa/validation.json` as the repair queue. Fix `error` findings before `warning` findings.
- For `transparent_rgb_residue` only, run the validator with `--fix-transparent-rgb` because it preserves visible pixels:

```bash
python "$SKILL_DIR/scripts/validate_source_bundle.py" /absolute/path/PetName.pet \
  --fix-transparent-rgb \
  --json-out /absolute/path/PetName.pet/qa/validation.json
```

- For identity, layout, alpha-edge, or state-semantics failures, read `references/qa-rubric.md`, repair the single frame/state as a candidate packet, pre-screen it, and ask for approval before replacing the source frame.
- After every repair, rerun validation. After export, inspect `qa/contact-sheet.png` for motion, row order, empty unused cells, and identity consistency.

### Scale And Footprint QA

- Fixed cell size is not the same as fixed character size. Every normalized frame must remain `192x208`, but the visible Pet footprint should stay consistent across states unless the state intentionally changes body scale. Compare visible sprite size against `idle` or `sources/canonical-base.png`, not only against the cell dimensions.
- When measuring sprite footprint, do not trust raw alpha bounds alone. First ignore or remove low-alpha residue, thin guide/ruler components, and tiny specks; then measure the largest real visible sprite component. This avoids border marks or cleanup residue making an undersized sprite look correctly framed.
- For size, crop, or scale repairs, render a full atlas-style preview that shows all state rows together, not only the repaired row contact sheet. Use the full-sheet comparison to catch cross-state scale mismatches before asking for approval or promoting frames.

## HTML Review Pages

Render review pages after candidate pre-screening and before human approval:

```bash
python "$SKILL_DIR/scripts/render_candidate_review_html.py" /absolute/path/PetName.pet \
  --action waiting \
  --output /absolute/path/PetName.pet/qa/waiting-review.html
```

Share the HTML file path with the human. The page must render sprite-action candidates in motion: use an existing `animated-preview.webp`/`.gif`, or let `render_candidate_review_html.py` build `animated-preview.webp` from `contact-sheet.png` for known Geist frame counts. A static contact sheet may remain visible or available as supporting evidence, but it must not be the only preview for animation-state approval. The **Choose** button should copy a sentence such as `I choose waiting-b for waiting.` back to the clipboard; the **Copy Prompt** button should copy that candidate's exact generation prompt. Do not promote candidates until the human responds with the chosen candidate id.

## References

- Read [references/contract.md](references/contract.md) before creating, validating, exporting, or installing a bundle.
- Read [references/generation-workflow.md](references/generation-workflow.md) before writing a character bible, generating new art, or building candidate packets.
- Read [references/qa-rubric.md](references/qa-rubric.md) before accepting, repairing, or visually reviewing frames.

## Scripts

- `scripts/validate_source_bundle.py`: checks frame counts, dimensions, alpha, empty frames, safe padding, transparent RGB residue, and green/cyan edge fringe. Use `--fix-transparent-rgb` only for invisible RGB cleanup.
- `scripts/export_geist_pet.py`: validates, composes `1536x1872` Geist atlas output, writes exported `pet.json`, writes `qa/contact-sheet.png`, and optionally installs into `${GEIST_HOME:-$HOME}/.geist/pets/<id>/`.
- `scripts/render_candidate_review_html.py`: renders `qa/<sprite-action>-review.html` from candidate packets with moving sprite previews, choose buttons, and copy-prompt buttons for human validation. It auto-builds `animated-preview.webp` from `contact-sheet.png` for known Geist animation states when an animated preview is missing.
