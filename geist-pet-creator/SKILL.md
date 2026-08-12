---
name: geist-pet-creator
description: Create, validate, repair, audit, and export consistent Geist-compatible Pet source bundles from approved alpha PNG frames. Use when Codex needs to make or fix a Geist Pet, Pet source bundle, character bible, Part Manifest, generated Pet candidates, sprite-frame QA, anatomy drift in a spritesheet, alpha PNG cleanup, human-in-the-loop art approval, an external image generator for Pet art, Geist pet.json metadata, spritesheet.webp export, or local Geist Pet installation. Also use when a Pet is derived from an existing character, cast, mascot, or franchise and its identity must be blended into the Geist house style, or when brainstorming Pet concepts, design variants, or a multi-character cast as a single concept sheet to choose from.
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

## Image Generation Modes

Pick the mode **once, at bundle setup, from what the running agent can actually do**, and record it in the bundle. Never re-decide it mid-bundle.

- **Built-in Image Generation** — use it when the running agent has its own image capability, such as Codex with `$imagegen`. No configuration, no key.
- **External Image Provider** — use it otherwise. Write `imagegen.json` into the bundle and `scripts/generate_candidates.py` makes the OpenRouter calls. It covers **every** drawing phase: `--action concept-sheet`, `--action canonical-base`, and each of the nine animation states. A human may name a different model for a single run.

The mode changes what draws the pixels. Approval gates, candidate packets, and subagent authority stay identical. Once a bundle has drawn its first candidate, that mode is fixed: switching mid-bundle makes the provenance recorded in every earlier candidate packet false. If the recorded mode becomes unavailable, say so and stop.

Read [references/image-providers.md](references/image-providers.md) before configuring or using the External Image Provider.

### Never repin a model from the catalog listing

`GET /api/v1/models` is **incomplete**. Models absent from it answer requests normally. Measured 2026-08-12: `openai/gpt-image-2` — this skill's default — is absent from that listing both authenticated and unauthenticated, and draws frames for about $0.023 each. So are `x-ai/grok-imagine-image-2.0` and `qwen/qwen-image-3-pro`.

Sessions have repeatedly "verified" a pinned model against that listing, concluded it was fake, and repinned working bundles onto `openai/gpt-5.4-image-2`, which **rejects the transparency parameters this pipeline sends**. The check looks rigorous and returns the wrong answer, so it produces confident, harmful edits.

The only authoritative test is a live request, and it costs about $0.01:

```bash
scripts/with_openrouter_key.sh python3 scripts/generate_candidates.py --verify-model openai/gpt-image-2
```

Run that before changing any `model` value in an `imagegen.json` or in `KNOWN_MODELS`. A pin outside `KNOWN_MODELS` is now refused locally with this same warning, so a bad pin fails on a cheap read instead of at the provider mid-run.

For generated or visibly changed art, stop at candidate packets until the human approves a specific option. A broad response such as "go", "continue", or "looks good" only authorizes the next generation step; it is not approval to promote generated art, normalize frames, export, or install unless the human explicitly approves the named candidate or variant. For deterministic cleanup that preserves visible art, such as clearing transparent RGB residue on already-approved frames, approval is not required.

## Core Workflow

1. Capture a Pet brief: name, personality, visual references, required props, forbidden changes, and target style. When the Pet is derived from something already recognizable, capture the source and read [references/identity-blend.md](references/identity-blend.md) before anything else.
2. Read `references/contract.md`, then write `pet.json` and `character-bible.md` before generating animation frames. `character-bible.md` must include a `## Part Manifest` table, because it is what every frame gets counted against later. A derived Pet also needs an `## Identity Blend` table, because it is what decides which source cues survive the house form.
3. **Draw a concept sheet first when the request is a brainstorm.** If the human names multiple characters — a cast, a crew, a roster, a franchise — or asks for multiple design directions for one Pet, draw **one** image holding every concept on an invisible grid before anything else is generated. Pre-screen it cell by cell, render `qa/concept-sheet-review.html`, and ask the human to choose cells by id. Read [references/generation-workflow.md](references/generation-workflow.md) § Concept Sheet Route. A request for one named Pet with no brainstorm skips this step.
4. Generate or choose canonical-base candidates as candidate packets under `sources/candidates/` using image generation for any new visible art. Pre-screen each packet, then render an HTML review page with prompts and choice controls before asking the human to choose one for `sources/canonical-base.png`. A chosen sheet cell re-enters this gate as its own sprite-scale candidate with the crop as Image 1 — a cell is a concept and is never written straight to `sources/canonical-base.png`.
5. For every sprite action/state, generate multiple candidate variants with image generation before producing source frames. Exception: generate and approve `running-right` first, then create `running-left` as a deterministic horizontal flip of the approved `running-right` frames unless the human explicitly requests independent left-facing art. Pre-screen every variant, render an HTML review page with prompts and choice controls, and ask the human to choose which variant to use for that action.
6. Normalize only the human-selected variant for each sprite action into `frames/<state>/<index>.png`.
7. Validate the source bundle and save machine-readable QA:

```bash
python "$SKILL_DIR/scripts/validate_source_bundle.py" /absolute/path/PetName.pet \
  --json-out /absolute/path/PetName.pet/qa/validation.json
```

8. Repair the smallest failing unit. Do not regenerate the whole Pet unless the canonical base or character bible is wrong.
9. Audit every frame for anatomy drift, and let deterministic repairs run:

```bash
python "$SKILL_DIR/scripts/audit_spritesheet.py" /absolute/path/PetName.pet --repair
```

Work `repairs.generative_repair_queue` from `qa/final-audit.json`: regenerate each queued frame as a candidate packet, get it approved, promote it, then audit again. Repeat until the queue is empty or the frames reach their 2-pass limit. Report the frames that reached the limit as a character-bible or prompt problem rather than promoting a third attempt.

10. Look at all 57 artwork cells on `qa/final-audit.html`, against the Part Manifest. Write a verdict for every cell into `qa/final-audit.json`, then prove none was skipped:

```bash
python "$SKILL_DIR/scripts/audit_spritesheet.py" /absolute/path/PetName.pet --verify-verdicts
```

11. Ask the human to approve the audit by its digest, and record that approval in `qa/approvals.json` with `approved_action: "final-audit"`.
12. Export. It refuses without an approved audit for these exact frames:

```bash
python "$SKILL_DIR/scripts/export_geist_pet.py" /absolute/path/PetName.pet \
  --output-dir /absolute/path/PetName.pet/final
```

13. Audit the written spritesheet before the Pet reaches anyone, because the WebP re-encode can damage alpha:

```bash
python "$SKILL_DIR/scripts/audit_spritesheet.py" /absolute/path/PetName.pet --mode post-export
```

A clean post-export run needs no attention. Report a mismatch and re-export instead of delivering.

Use `--install` only when the user wants the exported Pet installed into the local Geist catalog.

## Source Bundle

```text
PetName.pet/
  pet.json
  character-bible.md
  sources/
    canonical-base.png
    candidates/
      concept-sheet-01/        # brainstorm route only
        candidate.png          # the one sheet image
        candidate-context.json # grid, per-cell verdicts, identity locks
        cells/cell-04.png      # written by crop_gallery_cells.py
    references/
      geist-house-style.png    # required for a derived Pet
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
- Treat the canonical base and every animation state as separate sprite actions that each need their own human validation. Required action approvals are: `canonical-base`, `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`, and `final-audit`.
- `concept-sheet` is a **conditional** gate. It joins the required list only when the brainstorm route fires — multiple characters, or multiple design directions for one Pet. It never replaces `canonical-base`.
- `final-audit` is the last gate before export. It approves one exact set of pixels by `atlas_digest`, so changing any frame reopens it.
- A concept sheet satisfies the `canonical-base` gate's variant requirement: its cells are the options, and the human chooses by cell id such as `cell-04`. The chosen cell then returns through the `canonical-base` gate as a sprite-scale candidate before it becomes `sources/canonical-base.png`. Record both decisions in `qa/approvals.json`.
- **Pre-screen a sheet per cell, not as one candidate.** Write a verdict for every cell. Failing cells appear on the review page struck out and cannot be chosen. Regenerate the whole sheet only when fewer than 3 cells pass, or when the cell that failed is a character the human named. One weak cell among strong ones is information, not a reason to redraw the sheet.
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

## Character Identity Blend

A **derived Pet** is built from something already recognizable: a character, a cast, a mascot, a brand figure, a known object or animal. It is neither a small copy of that source nor a plain Geist wearing a hat. It is a blend, and it carries two locks instead of one: the **house form** every Pet shares, and the 4-6 **identity cues** that make this source nameable.

Resolve conflicts in this order, always:

1. **House form invariants never yield** — one compact rounded legless floating body, a single thick Sky outline (`#2FB8EC`), Cream body area (`#FFF4E2`), two Ink dot eyes (`#20201C`), one tiny mouth, exactly one centered Mango heart (`#FF7A33`), tiny attached arm nubs, flat fills, props thick and rounded and attached, no floor or shadow, readable at `192x208`.
2. **Identity cues yield only to the house form**, and outrank every style detail.
3. **Style detail yields freely.**

If a style simplification would erase a recognizable feature, keep the feature and simplify how it is drawn. If a recognizable feature would break a house-form invariant, keep the invariant and translate the feature.

Rank the cues, strongest first: the crown cue (hair or headwear silhouette) does most of the naming, then one or two flat color blocks, then **exactly one** attached prop, then at most two face landmarks, then expression. Countable cues become Part Manifest rows so the anatomy audit can count them. Record all of it, including the cues you dropped and why, in the `## Identity Blend` table in `character-bible.md`.

Attach two images to every derived generation call and name both in the prompt: Image 1 the identity reference, Image 2 the house-style reference at `$SKILL_DIR/assets/geist-house-style.jpg`. Copy that file into the bundle as `sources/references/geist-house-style.jpg` so the bundle stays reproducible. Write identity locks as physical description, never as the character's name — a name pulls the source's whole art style in with it.

Every derived Pet fails in one of two directions, and the fixes are opposites. **Franchise copy** means the source style won: re-prompt from the house form outward. **Generic blob** means the house form won: strengthen the crown cue and the silhouette, and do not add props. Run the naming, silhouette, and heart tests from [references/identity-blend.md](references/identity-blend.md) before any derived candidate reaches a human.

Three shipped galleries show the cue budget spent well and one shows it spent badly. Read [assets/README.md](assets/README.md) before writing identity locks for a new source.

When the human brainstorms rather than naming one finished Pet — a cast, a crew, a roster, a franchise, or several design directions for a single Pet — take the concept-sheet route: one sheet image with one mascot per cell on an invisible grid, one numbered identity-lock paragraph per cell in row-major order, human choice by cell id, then each chosen cell re-enters the normal `canonical-base` gate as its own sprite-scale candidate. A sheet cell is a concept, never a canonical base.

## Generation Rules

- Treat `character-bible.md` and `sources/canonical-base.png` as the identity lock for every frame. For a derived Pet, the `## Identity Blend` table is part of that lock and travels into every prompt alongside the Part Manifest.
- Draw canonical-base candidates and sprite-action candidate art with the active image generation mode. The candidate's visible pose, expression, motion read, and frame artwork should come from generated imagery, not from scripted transforms alone.
- Every generation call must produce a candidate packet: generated file path, exact prompt, input images, target state/frame/action, identity invariants, generation provenance, pre-screen result, and human-facing approval summary.
- **Once `canonical-base` is approved, variants vary motion only.** For each sprite action, vary candidates intentionally: for example subtle, energetic, and expressive motion reads. Keep all variants inside the character bible; do not create variants by changing identity, palette, props, or style.
- **Before `canonical-base` is approved, the concept sheet is where identity varies.** Cells may differ in silhouette, crown cue, prop choice, and palette accents — that is what a brainstorm is for. The house-form invariants never vary between cells: one compact rounded legless floating body, one thick Sky outline, Cream body area, two Ink dot eyes, one tiny mouth, exactly one centered Mango heart, tiny attached arm nubs, flat fills, no floor or shadow.
- Do not offer affine transforms, CSS/canvas motion, or code-distorted copies of the canonical base as final sprite-action candidates unless the human explicitly asks for deterministic prototyping. If used, label them as prototypes or archive them outside the active review set.
- Use code for processing generated art: slicing contact sheets, removing chroma-key backgrounds, alpha cleanup, resizing to `192x208`, validating frames, exporting atlases, and rendering HTML review pages.
- Prefer frame-by-frame or small state batches over whole-row strips. Never accept identity drift just because atlas geometry validates.
- Directional movement states are not literal leg-running. `running-right` must read as moving/gliding right. `running-left` must normally be the same sprite cycle as `running-right` with each approved frame horizontally flipped, not independently regenerated. Use lateral movement, drift, glide, lean, translation, soft squash/stretch, or trailing side/body shapes. Do not prompt for or accept legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics.
- `running` means active task work, not foot-running.
- Avoid detached effects, shadows, glows, motion trails, guide marks, white backgrounds, and chroma-key residue.
- For derived Pets, never carry these across from the source: legs, feet, shoes, realistic hands or faces, real weapons and blades, franchise titles, official logos, exact emblems, kanji, readable letters or numbers, aura and energy effects, speed lines, scenery, or the source's own outline color and rendering style.
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

### Anatomy QA

Anatomy drift is a frame disagreeing with the Part Manifest: a part missing, a part duplicated, or a part crossing the cell line. Every geometry check passes on a frame whose wing has vanished, so anatomy is settled by looking at all 57 artwork cells against the manifest. Read [references/qa-rubric.md](references/qa-rubric.md) § Anatomy QA for how to read the evidence.

Suspicion scores rank which frames to look at first. A frame scoring zero has been found unremarkable by six measurements, which is not the same as correct — and the anchor frame scores zero by construction.

Repair splits by whether the pixels already exist. Deterministic repair moves or clears existing pixels and writes in place after backing up to `sources/raw/repair-backups/`. Generative repair creates pixels, so it produces a candidate packet and waits for human approval like any other generated art. A frame gets at most 2 passes; after that, fix the character bible or the prompt.

Keep the flagged-frame count in your report even when repairs succeed, so a weak identity lock stays visible.

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

A concept sheet uses the same script with `--action concept-sheet`, and renders differently: one sheet image under a numbered row-major overlay grid, each cell showing its identity lock and its pre-screen verdict, failing cells struck out and unchoosable. Its **Choose** button copies `I choose cell-04 from the concept sheet.` Cell numbers are drawn by the review page and **never baked into the generated image** — baked text is unreliable and would land inside the crop when a cell becomes a reference.

## References

- Read [references/contract.md](references/contract.md) before creating, validating, exporting, or installing a bundle.
- Read [references/identity-blend.md](references/identity-blend.md) before creating any Pet derived from an existing character, cast, mascot, or franchise, and before building a concept sheet.
- Read [references/generation-workflow.md](references/generation-workflow.md) before writing a character bible, generating new art, or building candidate packets.
- Read [references/qa-rubric.md](references/qa-rubric.md) before accepting, repairing, or visually reviewing frames.
- Read [references/image-providers.md](references/image-providers.md) before configuring or using the External Image Provider.
- Read [measurements/2026-08-12-provider-eval.md](measurements/2026-08-12-provider-eval.md) before changing the default model, raising a spend cap, or arguing a model is better than the pinned one. It records what was measured, what it cost, and what it does not prove.
- Read [measurements/2026-08-12-concept-sheet-smoke.md](measurements/2026-08-12-concept-sheet-smoke.md) before changing the concept-sheet grid table, the cell cap, or how cells are cut. A sheet costs 1.5-2x a frame, the 12-cell cap held, and cutting cells on an even grid was measured clipping mascots that a model drew past the boundary.

## Assets

Reference images, attached to generation calls and read when judging a derived candidate. [assets/README.md](assets/README.md) reads each one cell by cell.

- `assets/geist-house-style.jpg`: the house form lock — twelve original Geist Pets, no source character among them. Attach as Image 2 on every derived generation call, and copy into the bundle as `sources/references/geist-house-style.jpg`.
- `assets/identity-cues-ranked.jpg`: how far a crown cue alone carries a read, and what a weak one costs.
- `assets/identity-cues-crew.jpg`: the one-prop budget, countable cues, and species tabs for sources that are not human-shaped.
- `assets/identity-cues-labeled.jpg`: the labeled-gallery convention, and how sparse a cue set can be and still name its source.
- `assets/identity-cues-franchise-copy.jpg`: a counter-example showing the franchise-copy failure mode. Never attach it as a style target.

## Scripts

- `scripts/validate_source_bundle.py`: checks frame counts, dimensions, alpha, empty frames, safe padding, transparent RGB residue, and chroma fringe on true boundary pixels. Use `--fix-transparent-rgb` only for invisible RGB cleanup. Cyan fringe detection is opt-in via `--detect-cyan-fringe`, because Pet outlines are often blue or teal and their antialiased edges read as cyan.
- `scripts/audit_spritesheet.py`: audits all 57 artwork cells for anatomy drift, asserts the 15 unused cells are transparent, ranks frames by suspicion, and renders `qa/final-audit.html`. `--repair` applies deterministic repairs and queues the rest; `--mode post-export` audits the written spritesheet; `--verify-verdicts` fails while any cell lacks an agent verdict.
- `scripts/generate_candidates.py`: draws through the External Image Provider at every phase, selected with `--action`: `concept-sheet` (one call, no canonical base), `canonical-base` (`--variants N`), or any of the nine animation states (one frame per call, canonical base and previous frame as references). Enforces `--max-images` and `--max-cost-usd` with per-action defaults, refuses a `model` pin outside `KNOWN_MODELS`, and answers `--verify-model <id>` with a live request when a model id is in doubt. `--state` remains as a deprecated alias for `--action`.
- `scripts/with_openrouter_key.sh`: resolves `OPENROUTER_API_KEY` from the macOS login keychain and execs the given command with it set in that child only. Use it for every provider call rather than exporting the key in a shell profile. A missing keychain item is an error, never a fallback.
- `scripts/eval_providers.py`: measures image models on reference-conditioned generation — cost, duration, mechanical QA, silhouette test — and writes a review page for the naming and blend judgements that stay human. Run it rather than trusting a model list or a price that has aged. Concept-sheet cases are scored on whether their cells are *comparable*: cell count, containment, scale spread, baseline spread, and row-major order read mechanically from an ordered body-hue probe.
- `scripts/export_geist_pet.py`: validates, requires an approved final audit for these exact frames, composes `1536x1872` Geist atlas output, writes exported `pet.json`, writes `qa/contact-sheet.png`, and optionally installs into `${GEIST_HOME:-$HOME}/.geist/pets/<id>/`.
- `scripts/render_candidate_review_html.py`: renders `qa/<sprite-action>-review.html` from candidate packets with moving sprite previews, choose buttons, and copy-prompt buttons for human validation. It auto-builds `animated-preview.webp` from `contact-sheet.png` for known Geist animation states when an animated preview is missing. `--action concept-sheet` renders the sheet page instead: numbered row-major cell overlay, per-cell identity lock and verdict, failing cells struck out.
- `scripts/crop_gallery_cells.py`: crops chosen cells out of an approved concept sheet using the grid recorded in `candidate-context.json`, writing `sources/candidates/<candidate-id>/cells/cell-NN.png`. It refuses a cell carrying a `fail` verdict and does not trim the paper margin, because trimming an off-white background needs a threshold and a wrong one eats the outline. Bundle scaffolding stays with the agent.

Four modules sit behind those scripts and are imported, not run:

- `scripts/geist_grid.py`: the atlas contract, and `FrameGrid`, which answers which file is frame N of a sprite action. Every finding names a path this module produced, so a finding always names a file that exists.
- `scripts/geist_pixels.py`: alpha primitives and the alpha threshold.
- `scripts/geist_manifest.py`: reads the Part Manifest and renders it into prompts, so generation and audit describe the same Pet.
- `scripts/geist_house.py`: the house form as prompt text, the concept-sheet grid table, and the row-major cell geometry. The generator, the cropper, and the eval all read it, so none of them can hold a private idea of where `cell-04` is.
