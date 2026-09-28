---
name: geist-pet-creator
description: Create, validate, repair, audit, and export Geist Pet source bundles from approved alpha PNG frames — character bible, Part Manifest, pet.json, spritesheet.webp, local install. Use for Pet art of any kind: drawing candidates through an image generator, sprite-frame QA, anatomy drift in a spritesheet, or human-in-the-loop approval. Also use when a Pet is derived from an existing character, cast, mascot, or franchise and must be blended into the Geist house style; when brainstorming Pet concepts, design variants, or a cast as one concept sheet to choose from; when a human delegates every design decision and wants a Pet built autonomously; or when accounting for what a Pet's art cost.
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

`GET /api/v1/models` is **incomplete**. Models absent from it answer requests normally. Measured 2026-08-12: `openai/gpt-image-2` — this skill's default — is absent from that listing both authenticated and unauthenticated, and draws frames for about $0.012 a call. So are `x-ai/grok-imagine-image-2.0` and `qwen/qwen-image-3-pro`.

Sessions have repeatedly "verified" a pinned model against that listing, concluded it was fake, and repinned working bundles onto `openai/gpt-5.4-image-2`, which **rejects the transparency parameters this pipeline sends**. The check looks rigorous and returns the wrong answer, so it produces confident, harmful edits.

The only authoritative test is a live request, and it costs about $0.01:

```bash
scripts/with_openrouter_key.sh python3 scripts/generate_candidates.py --verify-model openai/gpt-image-2
```

Run that before changing any `model` value in an `imagegen.json` or in `KNOWN_MODELS`. A pin outside `KNOWN_MODELS` is now refused locally with this same warning, so a bad pin fails on a cheap read instead of at the provider mid-run.

For generated or visibly changed art, stop at candidate packets until the human approves a specific option. A broad response such as "go", "continue", or "looks good" only authorizes the next generation step; it is not approval to promote generated art, normalize frames, export, or install unless the human explicitly approves the named candidate or variant. For deterministic cleanup that preserves visible art, such as clearing transparent RGB residue on already-approved frames, approval is not required.

That is the supervised default. Full automation moves most of those choices to the agent, and the next section says exactly which ones it does not move.

## Decision Modes

The image generation mode decides what draws the pixels. The **decision mode** decides who chooses between what it drew. They are independent — either drawing mode runs under either decision mode.

- **Supervised** is the default: a review page for every action, and a human choosing by candidate id.
- **Full Automation** is opt-in: the agent chooses, with two gates left standing.

Switch to full automation only on an explicit statement about **decisions** — "fully automate", "all decisions are up to you", "don't ask me, just build it". "Just do it", "hurry", and "go" are about speed rather than authority, so ask once which was meant. A mode is never inherited from momentum.

Modes mix per action: "automate the rest, show me options for `idle`" is one supervised action inside an automated build. Record the resolved mode on every decision record in `qa/approvals.json`, and pass `--mode auto|supervised` to `generate_candidates.py` so every ledger line carries it too.

### What full automation decides

| Phase | Under full automation |
| --- | --- |
| Concept sheet | **human gate stands** — see below |
| `canonical-base` | 2-3 options, agent chooses by the tie-break ladder |
| the nine animation states | agent promotes without asking; the review page is the record |
| generative repair queue | agent promotes, inside the existing 2-pass limit |
| `final-audit` | **human gate stands** — export refuses without it |
| install | separate explicit request, as always |

The **tie-break ladder**, in order: pre-screen status, then the naming, silhouette, and heart tests from [references/identity-blend.md](references/identity-blend.md), then footprint consistency against `idle` or the canonical base. Record the ranking and the reason on the decision record — a choice with no stated reason cannot be audited afterwards.

A candidate that fails pre-screen gets at most 2 regenerations, the same limit anatomy repair uses, and then the run stops and reports it as a character-bible or prompt problem. Never promote a frame already known to fail.

### A brainstorm still stops for a human

The concept sheet exists so a human can compare identities, so it stays a human gate even under full automation, and the route still fires on **detection** — multiple characters, or multiple design directions for one Pet. "Fully automate Pets for these six characters" draws the sheet and waits. Automation may not route around that gate by treating a cast as a list of jobs.

When nobody is available to choose, draw the sheet, pre-screen every cell, render `qa/concept-sheet-review.html`, then stop and report. That spends the $0.10 which makes the decision reviewable and withholds the ~$0.57 pass that depends on it.

Once cells are chosen, automation resumes. Rendering a chosen cell at sprite scale is execution, not an identity choice.

### Before and after an automated run

Before the first call, state the estimate and the ceiling: about **$1.11** for 57 frames, plus base options — and see § What A Pet Costs, which is now written against two measured ledgers rather than a projection. It is an announcement, not a request for confirmation — the authority was already granted.

When the frames are built, hand over one report:

- one line per state: the variant chosen, and the ladder reason it won
- cost estimated versus actual, and the ledger path
- the flagged-frame count from the anatomy audit
- every state that exhausted its 2 passes

Feedback naming a state re-runs that state as a single variant with the note folded into the prompt. If that fails pre-screen twice, escalate that one state to a 3-variant spread and ask. Read [references/generation-workflow.md](references/generation-workflow.md) § Sprite Action Variant Review for the per-action mechanics, and [references/image-providers.md](references/image-providers.md) § The spend ledger for what each run records.

## What A Pet Costs

A 57-frame pass on the default model costs about **$1.11** — 49 frames drawn at one billed call each, plus the 8 `running-left` frames flipped for free. Add roughly **$0.10–0.18** for canonical-base options and a concept sheet.

That figure is measured, not projected. Two full builds landed on a real ledger and agreed with each other:

| Build | Total | Calls | Per call | Clean 57-frame pass |
| --- | ---: | ---: | ---: | ---: |
| FarWatcher, 2026-08-12 | $2.10 | 84 | $0.0227 | $1.11 |
| FuseSprout, 2026-08-13 | $2.14 | 83 | $0.0246 | $1.20 |

Quote the lower one. A build landing near $1.20 is healthy; a build landing near $2.00 spent about 37% of itself on art it threw away, which is what both of these did.

**Every number here has one owner, and a defect is a number owned twice or not at all.** When a build comes in over budget, find the module that owns the number it got wrong and fix it there — patching a single run with `--extra-prompt` leaves the next build to rediscover it. Fifteen defects and the owner that closed each are in [references/cost-history.md](references/cost-history.md); read it when a build overruns or a defect looks familiar.

**What is still unmeasured, and owed:** every frame call carries two reference images, the canonical base and the previous frame, and that is the obvious suspect for a per-call price of $0.023. `eval_providers.py` already has the harness — draw one state with both references and one with the base only, then compare cost against identity drift. If the previous-frame reference is not earning its share, dropping it saves roughly **$0.55 per Pet**. If it is earning it, record that here and $1.11 stands as the floor.

### One variant per animation state

Draw **one**. Branch to alternatives only for a state that fails pre-flight or pre-screen, or where the human asked to see options — "explore the design ideas for each state" is that ask, and it gets 3.

Variants defend against a taste disagreement. They do not defend against a bad prompt: a bad prompt fails all three identically, at triple cost. On the measured build, six of nine actions were right on the first draw and the three that were not shared one prompt defect that no sibling would have solved.

`canonical-base` keeps its 3 in both decision modes. That choice is genuinely about taste, and it locks all 57 frames drawn against it. **Spend variance where it is cheap:** a base option costs about $0.012 and decides what every later frame is counted against; a second variant of a whole state costs about $0.09 and only changes how it moves.

### A run that stops early has already paid for its lesson

`generate_candidates.py` returns `ok: false` and names the check that failed when pre-flight vetoes a state. That is a prompt or a canonical-base problem. Fix the named cause — drawing the state again unchanged spends the same money for the same result.

**Every frame that was paid for is on disk**, whatever stopped the run. Each one lands in the candidate packet the moment the provider answers — the fitted cell in `frames/`, the raw provider image in `raw/`, and a line in `provenance.jsonl` — so a veto, a ceiling, or a kill loses nothing already bought. Redraw only the gap:

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action waiting --variant a --frames 3-5
```

A resumed run reads the packet's own earlier frame as the previous-frame reference, so the identity chain continues rather than restarting from the canonical base alone.

`canonical-base` runs report `growth_allowance` per candidate: how far that silhouette can still grow inside the cell before it touches the line. A base tight on both axes will fight all 57 later frames, and this review is the last moment when swapping it costs one call instead of a state. On the measured build, the base chosen for the strongest identity read had the least room, and caused five of six clipping failures.

## Core Workflow

1. Capture a Pet brief: name, personality, visual references, required props, forbidden changes, and target style. When the Pet is derived from something already recognizable, capture the source and read [references/identity-blend.md](references/identity-blend.md) before anything else.
2. Read `references/contract.md`, then write `pet.json` and `character-bible.md` before generating animation frames. `character-bible.md` must include a `## Part Manifest` table, because it is what every frame gets counted against later. A derived Pet also needs an `## Identity Blend` table, because it is what decides which source cues survive the house form. `pet.json` `description` must be a detailed signature paragraph (silhouette and crown cue, palette and face, prop, motion personality — see contract.md § Pet Metadata), never a generic one-liner; validation refuses a generic description.
3. **Draw a concept sheet first when the request is a brainstorm.** If the human names multiple characters — a cast, a crew, a roster, a franchise — or asks for multiple design directions for one Pet, draw **one** image holding every concept on an invisible grid before anything else is generated. Pre-screen it cell by cell, render `qa/concept-sheet-review.html`, and ask the human to choose cells by id. Read [references/generation-workflow.md](references/generation-workflow.md) § Concept Sheet Route. A request for one named Pet with no brainstorm skips this step.
4. Generate or choose canonical-base candidates as candidate packets under `sources/candidates/` using image generation for any new visible art. Pre-screen each packet, then render an HTML review page with prompts and choice controls before asking the human to choose one for `sources/canonical-base.png`. Under full automation, draw 2-3 options and choose by the tie-break ladder instead of asking. A chosen sheet cell re-enters this gate as its own sprite-scale candidate with the crop as Image 1 — a cell is a concept and is never written straight to `sources/canonical-base.png`.
5. For every sprite action/state, generate one candidate variant with image generation before producing source frames, and read § One variant per animation state before drawing a second. Exception: generate and approve `running-right` first, then run `--action running-left`, which flips those approved frames for free unless the human explicitly requests independent left-facing art. Pre-screen every variant and render an HTML review page with prompts and choice controls; under supervised mode ask the human to choose, and under full automation the page is the record of a choice already made.
6. Normalize only the selected variant for each sprite action into `frames/<state>/<index>.png`.
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

`--repair` settles cell bleed first, for the whole state at once: one shared rescale from the row's union bounding box, which moves existing pixels and keeps every frame in proportion to the others. Then it repairs per frame. Last, it registers every state onto the bundle's one size and one anchor, so a Pet cannot change size or hop when its state changes — read § Scale And Footprint QA before widening a travel budget.

Work `repairs.generative_repair_queue` from `qa/final-audit.json`: regenerate each queued frame as a candidate packet, get it approved — or promote it by the ladder under full automation — then audit again. Repeat until the queue is empty or the frames reach their 2-pass limit. Report the frames that reached the limit as a character-bible or prompt problem rather than promoting a third attempt.

`repairs.flagged_for_review` is a separate list and costs nothing. Those frames scored high on suspicion with no hard error, so they are ranked for a look, not queued for a redraw. Look at them on `qa/final-audit.html` and write a verdict; a frame that is simply moving the way its state asks needs no art.

10. Look at all 57 artwork cells on `qa/final-audit.html`, against the Part Manifest. Write a verdict for every cell into `qa/final-audit.json`, then prove none was skipped:

```bash
python "$SKILL_DIR/scripts/audit_spritesheet.py" /absolute/path/PetName.pet --verify-verdicts
```

11. Ask the human to approve the audit by its digest, then record their answer with `scripts/geist_approvals.py --action final-audit --atlas-digest <digest>`, which owns the schema. This gate is human in **both** decision modes, so an automated build ends here and waits.
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
    spend.jsonl              # one line per provider call, appended as it happens
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

- Under supervised mode, do not promote generated art into `sources/canonical-base.png` or `frames/` until a human approves it. Under full automation the agent decides and records the decision — except at the two gates below, which never move.
- **`final-audit` is a human gate in both decision modes, and so is a concept sheet whenever the brainstorm route fires.** Everything else in the list below is a decision that full automation may make for itself.
- Treat the canonical base and every animation state as separate sprite actions that each need their own recorded decision. Required action decisions are: `canonical-base`, `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`, and `final-audit`.
- `concept-sheet` is a **conditional** gate. It joins the required list only when the brainstorm route fires — multiple characters, or multiple design directions for one Pet. It never replaces `canonical-base`.
- `final-audit` is the last gate before export. It approves one exact set of pixels by `atlas_digest`, so changing any frame reopens it.
- A concept sheet satisfies the `canonical-base` gate's variant requirement: its cells are the options, and the human chooses by cell id such as `cell-04`. The chosen cell then returns through the `canonical-base` gate as a sprite-scale candidate before it becomes `sources/canonical-base.png`. Record both decisions in `qa/approvals.json`.
- **Pre-screen a sheet per cell, not as one candidate.** Write a verdict for every cell. Failing cells appear on the review page struck out and cannot be chosen. Regenerate the whole sheet only when fewer than 3 cells pass, or when the cell that failed is a character the human named. One weak cell among strong ones is information, not a reason to redraw the sheet.
- For each sprite action, provide one candidate variant in both decision modes; § One variant per animation state says when to draw more. `canonical-base` is the standing exception at 3. Exception: `running-left` should normally be a single deterministic mirror candidate made from the approved `running-right` row, with its own review page and approval. Each variant must include the generated image or contact sheet, the exact prompt or deterministic operation used to create it, and a compact pre-screen summary.
- For each approval gate, create an HTML review page at `qa/<sprite-action>-review.html` using `scripts/render_candidate_review_html.py`. For animation states, the page must render each candidate as a moving sprite preview, not only as a static contact sheet. The page must also show all passing candidates, exact prompts, pre-screen summaries, a **Choose** button, and a **Copy Prompt** button for each candidate.
- Under supervised mode, ask the human to choose one variant by candidate id before promoting that action. Do not infer approval from "go" or from approval of a different action, and do not infer full automation from either.
- Pre-screen every candidate first. Reject obvious identity, layout, alpha, state-semantics, or prompt-compliance failures without asking the human.
- Show the human only pre-screened candidates plus a compact approval context: what was generated, the prompt used, what it must preserve, what passed, what risks remain, and the exact decision needed.
- Record approvals with `scripts/geist_approvals.py`, which owns the schema, rather than by writing `qa/approvals.json` by hand. The file is a **top-level JSON array** of records in the shape [references/contract.md](references/contract.md) § Approval Contract documents: `candidate_id`, `approved_action`, `approved_for`, `source`, `decision`, `decided_by`, `approver_note`, `decided_at`. `approved_action`, `decision` and `decided_by` are the three that were in no prose list and are exactly the ones the export gate matches on; two builds lost export attempts writing `{"approvals": [...]}` instead. A `final-audit` record also needs the `atlas_digest`, which is what stops an approval outliving the art it covered.

  ```bash
  python "$SKILL_DIR/scripts/geist_approvals.py" /absolute/path/PetName.pet \
    --action final-audit --atlas-digest <digest from qa/final-audit.json> \
    --note "what the human actually said"
  ```
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
- **Once `canonical-base` is approved, variants vary motion read and expression.** For each sprite action, vary candidates intentionally: for example subtle, energetic, and expressive motion reads, and the posture and expression language that go with them. Expression is how `waiting` reads differently from `idle`, and it stays inside the Part Manifest, so the anatomy audit still counts it. Keep all variants inside the character bible; never create a variant by changing identity, palette, props, or style.
- **Before `canonical-base` is approved, the concept sheet is where identity varies.** Cells may differ in silhouette, crown cue, prop choice, and palette accents — that is what a brainstorm is for. The house-form invariants never vary between cells: one compact rounded legless floating body, one thick Sky outline, Cream body area, two Ink dot eyes, one tiny mouth, exactly one centered Mango heart, tiny attached arm nubs, flat fills, no floor or shadow.
- Do not offer affine transforms, CSS/canvas motion, or code-distorted copies of the canonical base as final sprite-action candidates unless the human explicitly asks for deterministic prototyping. If used, label them as prototypes or archive them outside the active review set.
- Use code for processing generated art: slicing contact sheets, removing chroma-key backgrounds, alpha cleanup, resizing to `192x208`, validating frames, exporting atlases, and rendering HTML review pages.
- Prefer frame-by-frame or small state batches over whole-row strips. Never accept identity drift just because atlas geometry validates.
- Directional movement states are not literal leg-running. `running-right` must read as moving/gliding right, carried by lateral movement, drift, glide, lean, translation, soft squash/stretch, or trailing side/body shapes. `running-left` must normally be the same sprite cycle with each approved frame horizontally flipped, not independently regenerated. The frame prompt now says this to the model itself, for the four states whose name pulls hardest towards legs: `geist_house.LEGLESS_MOTION`, applied to `running-right`, `running-left`, `running` and `jumping`. A frame that comes back with legs, feet, shoes, knees or a foot-step pose anyway is a pre-screen reject, and a second one is a prompt problem rather than a redraw.
- `running` means active task work, not foot-running.
- `failed` shows only sad/negative animation in every frame — drooping, downturned, downcast, deflated. Any happy, celebratory, or neutral frame in the row is a pre-screen reject.
- Every animation state must move the Pet's signature smoothly: the face (eyes, mouth) plus at least one other body part (arm nubs, crown cue, prop, palette accents) visibly animate in a way that fits the state and the Pet's personality, with smooth continuous transitions and a last frame that flows back into the first. Body translation alone is unfinished art.
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

- For `green_cyan_fringe`, run the validator with `--fix-green-fringe`. Every chroma-path frame carries some spill, the cleanup only pulls a semi-transparent edge pixel's hue to its own luminance, and it reads the same constants the gate does — so it needs no approval and cannot drift from what it is fixing.
- For identity, layout, alpha-edge, or state-semantics failures, read `references/qa-rubric.md`, repair the single frame/state as a candidate packet, pre-screen it, and ask for approval before replacing the source frame.
- After every repair, rerun validation. After export, inspect `qa/contact-sheet.png` for motion, row order, empty unused cells, and identity consistency.

### Anatomy QA

Anatomy drift is a frame disagreeing with the Part Manifest: a part missing, a part duplicated, a part crossing the cell line, or **a part that keeps its count and changes its shape**. Every geometry check passes on a frame whose wing has vanished, so anatomy is settled by looking at all 57 artwork cells against the manifest. Read [references/qa-rubric.md](references/qa-rubric.md) § Anatomy QA for how to read the evidence.

The fourth kind is the one a count can never catch, and it took a build to find: a `failed` row came back with the connected face glyph replaced by separate eyes and a detached frown, satisfying `mouth shape | 1` exactly. Two things look for it now, and neither replaces the other. The manifest's **`Shape` column** goes into every frame prompt, so the model is told. **Counting ink components** against the canonical base's own count is what notices when it did not listen — one glyph in all 57 cells on that build, three in the drifted row — and it runs in pre-flight too, where it stops a state at frame 1 instead of at frame 8.

Suspicion scores rank which frames to look at first. A frame scoring zero has been found unremarkable by six measurements, which is not the same as correct — and the anchor frame scores zero by construction. **A score never buys art.** Up to 40 of its points come from bounding-box displacement alone, so a `jumping` or directional frame can cross the flag by doing exactly what its state is for; those land in `flagged_for_review`, and only a hard error or a stray fragment reaches the repair paths.

Repair splits by whether the pixels already exist. Deterministic repair moves or clears existing pixels and writes in place after backing up to `sources/raw/repair-backups/`. Generative repair creates pixels, so it produces a candidate packet and waits for human approval like any other generated art. A frame gets at most 2 passes; after that, fix the character bible or the prompt.

Keep the flagged-frame count in your report even when repairs succeed, so a weak identity lock stays visible.

### Scale And Footprint QA

Fixed cell size is not fixed character size. Both are settled in code now, once per bundle, because an eye comparing nine rows is exactly what let a Pet ship 5.6% larger in one state than another.

`scripts/geist_registration.py` owns it. The **ruler** is `sources/canonical-base.png` — the identity lock is also the size lock. The **anchor** is bbox centre horizontally, base line vertically. `geist_house.MOTION_BUDGET` says which states may leave that anchor: `jumping` vertically, the three directional states horizontally, and the rest pinned. Widen a budget there rather than per run — a budget set in one run is a rule the next build never sees.

**`geist_house.SIZE_BUDGET` is its twin, and answers the other half.** `MOTION_BUDGET` says where a body may go; `SIZE_BUDGET` says how big it may get once it is there, as the ratio between a state's largest and smallest frame. `failed` deflates and `jumping` squashes, so both are budgeted; everything else is pinned and every frame is scaled onto the state's median. An undeclared state pins, for the same reason it does not float.

The cause decides what the fix can be. Each frame is drawn with the previous one attached as a reference, so size **ratchets along the chain** and frames 00–01 come back smallest every time. That is a property of the drawing order, and prompt text does not reach it:

> A SIZE LOCK in `--extra-prompt` took `idle` from 1.41x to 1.14x once, the next state came back at **0.54x** and was killed by pre-flight, and a third landed at 1.46x. Three paid redraws, nothing bought. Normalising to the state median is deterministic, costs nothing, and landed all five pinned states at 1.01–1.03x in one pass.

**Declare a size change where it is honoured: `SIZE_BUDGET`.** That is the only place a size instruction has an owner, and from there it is enforced for free on every later build.

- The generator applies the ruler as a state completes, from every frame of the state rather than from its frame 0. A frame 0 is a pose; a median over the state is the Pet. **Pre-flight judges drift the same way** — against the running median of the frames drawn so far, live for the whole state, not against frame 0 for the first two frames. Measuring is free; only drawing costs.
- `audit_spritesheet.py --repair` fixes a bundle that already exists, and reports every move under `repairs.registered`. It settles size twice: **within** a state against `SIZE_BUDGET`, then **between** states towards the median state rather than the base's absolute size, so a healthy bundle is left alone. It spends nothing — rescales and whole-pixel translations buy no art.
- Registration runs after the refit and the stray-fragment pass, because a speck stretches the bounding box it anchors to. Within-state size runs before the cross-state rescale, because the rescale is derived from a median that a ratchet would otherwise have moved.
- A `--repair` pass that changes nothing but registration still **re-stamps the atlas digest**. It did not, and an approval then named pixels that no longer existed: export refused, and the human's approval had to be carried across with a before-and-after fingerprint. No money lost, and a gate whose integrity is in question is expensive anyway.
- Look at the full sheet on `qa/final-audit.html` before approving. Registration fixes what it can measure; a body that reads wrong at the right size on the right anchor is a character-bible problem.

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
- Read [references/cost-history.md](references/cost-history.md) when a build overruns its budget, when a defect looks familiar, or before relaxing any gate in § What A Pet Costs. Fifteen defects across three builds, each with the owner that closed it.
- Read [measurements/2026-08-12-provider-eval.md](measurements/2026-08-12-provider-eval.md) before changing the default model, raising a spend cap, or arguing a model is better than the pinned one. It records what was measured, what it cost, and what it does not prove.
- Read [measurements/2026-08-12-concept-sheet-smoke.md](measurements/2026-08-12-concept-sheet-smoke.md) before changing the concept-sheet grid table, the cell cap, or how cells are cut. A sheet costs 1.5-2x a frame, the 12-cell cap held, and cutting cells on an even grid was measured clipping mascots that a model drew past the boundary.
- Read [measurements/2026-08-12-sprite-registration.md](measurements/2026-08-12-sprite-registration.md) before changing how a frame is scaled or placed into its cell — `CellTransform`, `refit_state`, or anything that decides where the body lands. It is why the anchor is a declared constant rather than a measured bounding box, and it records the measurement showing a body's bbox centre moving 29px across one state while its base line moves 0.

## Assets

Reference images, attached to generation calls and read when judging a derived candidate. [assets/README.md](assets/README.md) reads each one cell by cell.

- `assets/geist-house-style.jpg`: the house form lock — twelve original Geist Pets, no source character among them. Attach as Image 2 on every derived generation call, and copy into the bundle as `sources/references/geist-house-style.jpg`.
- `assets/identity-cues-ranked.jpg`: how far a crown cue alone carries a read, and what a weak one costs.
- `assets/identity-cues-crew.jpg`: the one-prop budget, countable cues, and species tabs for sources that are not human-shaped.
- `assets/identity-cues-labeled.jpg`: the labeled-gallery convention, and how sparse a cue set can be and still name its source.
- `assets/identity-cues-franchise-copy.jpg`: a counter-example showing the franchise-copy failure mode. Never attach it as a style target.

## Scripts

- `scripts/validate_source_bundle.py`: checks frame counts, dimensions, alpha, empty frames, safe padding, transparent RGB residue, and chroma fringe on true boundary pixels. `--fix-transparent-rgb` clears invisible RGB; `--fix-green-fringe` desaturates chroma spill on boundary pixels, reading the same rule and thresholds the gate reads so the two cannot disagree. Cyan fringe detection is opt-in via `--detect-cyan-fringe`, because Pet outlines are often blue or teal and their antialiased edges read as cyan.
- `scripts/audit_spritesheet.py`: audits all 57 artwork cells for anatomy drift, asserts the 15 unused cells are transparent, ranks frames by suspicion, and renders `qa/final-audit.html`. `--repair` refits any bleeding state by one shared factor, applies per-frame deterministic repairs, registers every state onto the bundle's one size and anchor, queues frames with a hard error the pixels cannot fix, and lists suspicion-only frames under `flagged_for_review` without spending anything. `--mode post-export` audits the written spritesheet; `--verify-verdicts` fails while any cell lacks an agent verdict.
- `scripts/generate_candidates.py`: **the only executable that spends money.** Draws every phase — `--action concept-sheet`, `canonical-base`, or any of the nine animation states, one frame per call with the canonical base and previous frame as references. `--action running-left` mirrors the approved `running-right` row for zero calls. Run `--help` for the flags; the rules it enforces are owned elsewhere — pre-flight and resuming in § A run that stops early, sizing and placement in § Scale And Footprint QA, transparency and backdrop in [references/image-providers.md](references/image-providers.md).
- `scripts/with_openrouter_key.sh`: resolves `OPENROUTER_API_KEY` from the macOS login keychain and execs the given command with it set in that child only. Use it for every provider call rather than exporting the key in a shell profile. A missing keychain item is an error, never a fallback.
- `scripts/eval_providers.py`: measures image models on reference-conditioned generation — cost, duration, mechanical QA, silhouette test — and writes a review page for the naming and blend judgements that stay human. Run it rather than trusting a model list or a price that has aged. Concept-sheet cases are scored on whether their cells are *comparable*: cell count, containment, scale spread, baseline spread, and row-major order read mechanically from an ordered body-hue probe.
- `scripts/export_geist_pet.py`: validates, requires an approved final audit for these exact frames, composes `1536x1872` Geist atlas output, writes exported `pet.json`, writes `qa/contact-sheet.png`, and optionally installs into `${GEIST_HOME:-$HOME}/.geist/pets/<id>/`.
- `scripts/render_candidate_review_html.py`: renders `qa/<sprite-action>-review.html` from candidate packets with moving sprite previews, choose buttons, and copy-prompt buttons for human validation. It auto-builds `animated-preview.webp` from `contact-sheet.png` for known Geist animation states when an animated preview is missing. `--action concept-sheet` renders the sheet page instead: numbered row-major cell overlay, per-cell identity lock and verdict, failing cells struck out.
- `scripts/spend_report.py`: reports what a Pet's art cost, from a bundle, a directory of bundles, or the machine-wide ledger with `--home`. Needs no credential, which is why it is not a flag on `generate_candidates.py`. `--record` appends a line for a draw this pipeline did not make, which is how Built-in Image Generation gets counted; those lines carry `cost_usd: null`, because an invented price in a file that reads like a receipt is worse than an honest gap.
- `scripts/crop_gallery_cells.py`: crops chosen cells out of an approved concept sheet using the grid recorded in `candidate-context.json`, writing `sources/candidates/<candidate-id>/cells/cell-NN.png`. It refuses a cell carrying a `fail` verdict and does not trim the paper margin, because trimming an off-white background needs a threshold and a wrong one eats the outline. Bundle scaffolding stays with the agent.

Seven modules sit behind those scripts and are imported, not run. **Each is the owner of the numbers listed against it** — the one place that number is decided, so every caller reads the same answer. Every defect the 2026-08 builds found was a number owned twice or not at all, which is why a fix belongs in one of these rather than in a caller.

- `scripts/geist_grid.py`: the atlas contract, and `FrameGrid`, which answers which file is frame N of a sprite action. Every finding names a path this module produced, so a finding always names a file that exists.
- `scripts/geist_pixels.py`: alpha primitives and the alpha threshold, plus `ink_components`/`component_count` — the connected-component pass the generator uses to catch a detached mark before it costs a state, and the auditor uses to rank a frame.
- `scripts/geist_manifest.py`: reads the Part Manifest and renders it into prompts, so generation and audit describe the same Pet. Counts **and** the optional `Shape` column, because a part that keeps its count while changing its shape satisfies a count-only manifest completely.
- `scripts/geist_house.py`: the house form as prompt text, the concept-sheet grid table, and the row-major cell geometry. The generator, the cropper, and the eval all read it, so none of them can hold a private idea of where `cell-04` is. It also holds the blocks every frame prompt carries — `FRAMING`, `LEGLESS_MOTION`, `FLAT_FIELD`, `SIGNATURE_MOTION` and `SMOOTH_LOOP`, plus `FAILED_MOOD` for the `failed` state — and the two budget tables, `MOTION_BUDGET` and `SIZE_BUDGET`.
- `scripts/geist_registration.py`: how big the Pet is and where it sits. Reads the ruler off `sources/canonical-base.png`, holds the anchor, translates frames back onto it inside `MOTION_BUDGET`, and holds each frame's size inside `SIZE_BUDGET`. The generator and the auditor both import it, so a state cannot be born at one size and audited against another.
- `scripts/geist_approvals.py`: the `qa/approvals.json` schema — one writer and one reader, in one place, because a schema whose only definition is its reader is a schema every writer has to reverse-engineer after an export has already refused.
- `scripts/geist_spend.py`: the ledger — line schema, the two paths, the append, and the rollup. Lines are appended the moment a provider answers rather than when a packet lands, because a run killed at a ceiling spends real money and writes no packet.
