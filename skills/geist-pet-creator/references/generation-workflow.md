# Generation Workflow

Use this guide before creating new Pet art.

## Pet Brief

Capture:

- Pet name and one-sentence description
- Personality and state behavior
- Visual references
- Source, when the Pet is derived from something already recognizable — a character, cast, mascot, brand figure, or known object — plus the cues the human expects to survive
- Required features that must never drift
- Forbidden changes
- Target style and readability constraints

A derived Pet changes what happens next: read [identity-blend.md](identity-blend.md) before writing the character bible, and again before the first generation call.

## Character Bible

Write `character-bible.md` before generating frames. Include:

- Silhouette: body shape, proportions, scale, anchor point
- Palette: named colors and materials
- Face landmarks: eye shape, eye spacing, mouth placement, face area
- Props and accessories: side, shape, colors, attachment points
- Motion personality: how this Pet idles, asks, works, fails, and reviews — per state, which face landmarks and which other body parts (arm nubs, crown cue, prop, palette accents) move, and how. This is the signature the frame prompts animate; a state with no entry here gets generic motion
- Avoidances: marks, effects, styles, objects, or expressions that would break identity
- **Identity Blend** (derived Pets only): the source, its ranked cues, how each was translated, and which were dropped
- **Part Manifest**: every part, how many times it may appear, its side, and its attachment point

### Writing the Part Manifest

The Part Manifest is what turns "the hand looks wrong" into "the hand appears twice". Read the table format in [contract.md](contract.md) § Part Manifest Contract, then fill it from the approved canonical base.

Two judgements decide each row:

- **The low bound is about poses that hide the part.** A wing behind a side-on body is correct art, so a wing that can hide gets `1-2`, not `2`. Set the low bound by asking which states legitimately conceal the part.
- **The high bound is about drift.** Image generation duplicates limbs, and the high bound is what catches it. Keep the high bound at the true count and mark `Never duplicated` on any part that must never exceed it.

Set the manifest before generating frames. A manifest written afterwards tends to describe the frames that exist rather than the Pet that was intended.

### Writing the Identity Blend

A derived Pet carries a second table, `## Identity Blend`, above the Part Manifest. Read [identity-blend.md](identity-blend.md) for the table shape and the cue budget, then fill it before the canonical base exists.

Three judgements decide the table:

- **Rank decides what gets protected.** The crown cue — hair or headwear silhouette — is what a viewer reads first at `192x208`, so it is rank 1 in almost every Pet. A cue ranked below the prop is a cue you will lose during animation, and losing it should be a decision rather than a surprise.
- **Translation is where the house form wins.** Write the Geist form of the cue, not the source's rendering. “One thick rounded brass message capsule attached at the side” is a translation; asking to reproduce a detailed source prop is not.
- **Dropped cues need their reason recorded.** A cue dropped for the house form, for the sprite scale, or for competing with the Mango heart will come back during repair unless the rejection is written down.

Countable cues get Part Manifest rows too, with the count that makes drift visible: `sword shape | 3 | back | body | Never duplicated`.

## Canonical Base

Create `sources/canonical-base.png` as a full-body alpha or clean-background reference. It is not enough for the base to look nice; it must be simple enough to preserve across all animation states at `192x208`.

Generate base variants as candidate packets first, using image generation for new visible art. The agent must pre-screen each candidate. Quick and Studio show the passing options and ask the human to choose an exact candidate id. Full Automation lets the agent choose by the documented tie-break ladder and records the reason before copying it to `sources/canonical-base.png`.

How many variants depends on whether a concept sheet ran:

- **A sheet ran.** One variant. The sheet already presented the options and the human already chose; this call renders the chosen cell at sprite scale. Raise the count only when that render loses the identity.
- **No sheet ran.** Three variants, the normal per-action minimum, because nothing has shown the human options yet.

For a derived Pet, attach two images to every base call and name both roles in the prompt: Image 1 the identity reference, Image 2 the house-style reference. The skill ships the house-style image at `$SKILL_DIR/assets/geist-house-style.jpg`; copy it into the bundle as `sources/references/geist-house-style.jpg` so the packet stays reproducible. Keep those roles in that order for the whole bundle, and state in the prompt which one wins on conflict. Pre-screen the result with the naming, silhouette, and heart tests from [identity-blend.md](identity-blend.md) before it reaches the human.

Read [asset-guide.md](asset-guide.md) before using the bundled house-style reference. Use only original or user-authorized identity references; do not ship third-party character galleries with a bundle.

### Concept Sheet Route

The route fires on a **brainstorm**, in either of two shapes:

- **Multiple characters** — a cast, a crew, a roster, a franchise.
- **Multiple design directions for one Pet** — "brainstorm some variants", "show me a few takes on this".

It does not fire for a request naming one Pet with one direction. It never fires for sprite-action variants: those stay separate candidate packets, because animation approval needs a moving preview per variant and a grid of contact sheets is strictly worse than what the per-action review already gives.

Draw **one image**, not one image per concept. One call, an invisible grid, one complete centered mascot per cell, equal scale and baseline, warm off-white paper, no dividers, no text. Cells drawn in the same call share scale, weight, and lighting, so they can be compared; cells drawn in separate calls cannot, and comparability is the entire reason the sheet exists.

#### Grid and aspect ratio

Set `aspect_ratio` to match the grid on every sheet call. A square request for a 5x2 grid letterboxes the cells and shrinks every mascot inside them.

**Only three aspect ratios actually draw: `1:1`, `3:2`, `4:3`.** Everything else fails, in one of two ways that look nothing alike:

- A ratio outside the provider's schema — `3:1`, `5:2` — is rejected as a `ZodError`.
- A ratio the schema accepts but no provider serves — `2:1`, `4:1`, `8:1`, `16:9` — is rejected with `No provider for <model> supports the requested parameters`.

The second is the trap. The schema listing looks authoritative, a ratio drawn from it looks validated, and the request still dies. **Choose the grid to fit the ratio, never the ratio to fit the grid.** `geist_house.py` holds the verified set and refuses anything else locally, before a call is made.

Counts that do not tile one of the three ratios take the next grid up and leave cells empty. That wastes a little canvas and risks the model drawing into the gap, which pre-screening catches — a long thin cell is not recoverable at all.

| Cells | Grid | Aspect ratio | Rects | Empty | Cell shape |
| ---: | --- | --- | ---: | ---: | --- |
| 3 | 2x2 | 1:1 | 4 | 1 | square |
| 4 | 2x2 | 1:1 | 4 | 0 | square |
| 5 | 3x2 | 3:2 | 6 | 1 | square |
| 6 | 3x2 | 3:2 | 6 | 0 | square |
| 8 | 3x3 | 1:1 | 9 | 1 | square |
| 9 | 3x3 | 1:1 | 9 | 0 | square |
| 10 | 4x3 | 4:3 | 12 | 2 | square |
| 12 | 4x3 | 4:3 | 12 | 0 | square |

Twelve is the cap. Split anything larger across two sheets: a cell too small to name is not a concept, it is a smudge. Maintainer measurements for this limit live in the repository's root `evidence/` directory and are not part of the installed skill.

**Do not assume the model puts its rows where the even grid says.** One model drew its first row 20 pixels past the even-thirds boundary, and cutting there would have shaved the bottom of every mascot in that row. `crop_gallery_cells.py` snaps to the gutters between the drawn rows for this reason; it warns and falls back to the even grid when it cannot read them.

#### Steps

1. **Decide where the sheet lives, by fan-out.** Many characters get a staging bundle, `<Thing>Concepts.pet`, because one sheet spawns many Pets. One character's variants go straight into the target `<Name>.pet` — a staging bundle for a single Pet is overhead with nothing to justify it. Either way the packet is `sources/candidates/concept-sheet-01/`.
2. **Write one numbered identity-lock paragraph per cell**, as physical description, in the exact row-major order the grid is read in. Never a character's name.
3. **Draw the sheet.** One call. Under the External Image Provider that is `--action concept-sheet`.
4. **Pre-screen every cell and record a verdict for each**, into `cells[]` in `candidate-context.json`.
5. **Render `qa/concept-sheet-review.html`** with `render_candidate_review_html.py --action concept-sheet`.
6. **Ask the human to choose by cell id.**
7. **Crop the chosen cells** with `crop_gallery_cells.py`, then carry each crop into the `canonical-base` gate as Image 1.

#### What may vary between cells

Cells are allowed to differ in silhouette, crown cue, prop choice, and palette accents. That is what a brainstorm is.

The house-form invariants never vary between cells: one compact rounded legless floating body, one thick Sky outline, Cream body area, two Ink dot eyes, one tiny mouth, exactly one centered Mango heart, tiny attached arm nubs, flat fills, no floor or shadow. A sheet whose cells disagree about the house form is not a set of options, it is a set of mistakes.

This licence ends at `canonical-base` approval. From there on, sprite-action variants vary motion read and expression only — never identity, palette, props, or style.

#### When a cell fails pre-screen

Do not throw the sheet away for one bad cell. Mark the cell `fail` with a short note; the review page strikes it out and makes it unchoosable, and `crop_gallery_cells.py` refuses to crop it.

Redraw the whole sheet only when **fewer than 3 cells pass**, or when the failing cell is a character the human named by name. One weak cell among strong ones is information about that identity lock, not a reason to spend another call.

#### Cell ids and labels

Cells are numbered row-major from 1, and addressed as `cell-04`. The identity-lock paragraphs are already numbered row-major, so the paragraph number and the cell id are the same number — no translation layer, and nothing to get out of step.

**Never bake cell numbers into the generated image.** Image generators render text unreliably, and a baked label lands inside the crop when the cell becomes Image 1 for the next call. The review page draws the numbered overlay instead.

#### A cell is a concept

A sheet cell is a concept, not a canonical base. Each chosen cell re-enters the `canonical-base` gate as its own sprite-scale candidate, with the crop as Image 1, before anything is written to `sources/canonical-base.png`. A 300px crop from a shared sheet cannot be the identity lock that all 57 frames are counted against.

#### V2 refinement

When a sheet reads generic, run a second round that keeps the same row-major families and the same layout, and strengthens the identity locks themselves. Adding an accessory to a cell that failed the naming test rarely fixes it; a stronger crown cue usually does.

## Sprite Action Variant Review

Every sprite action/state requires its own recorded decision before source frames are written — a human choice in Studio, an agent choice for Quick or Full Automation. Canonical-base choice remains human in Quick and Studio. The required sprite actions are:

- `canonical-base`
- `idle`
- `running-right`
- `running-left`
- `waving`
- `jumping`
- `failed`
- `waiting`
- `running`
- `review`

For each sprite action:

1. Generate variants with the active image generation capability: **3** in Studio unless the human specifies another count, **1** in Quick or Full Automation.
2. Store each variant as its own candidate packet or as a clearly named variant inside an action candidate set.
3. Include the exact generation prompt for every variant in `prompt.md`.
4. Pre-screen each variant and reject obvious failures before review.
5. Render an HTML review page with candidate id, moving sprite preview, prompt, preserved identity traits, risks, a **Choose** button, and a **Copy Prompt** button for every passing variant. Contact sheets may appear as supporting artifacts, but animation-state review must show motion.
6. In Studio, wait for the human to choose one candidate id. In Quick or Full Automation, choose by the ladder below and record the reason.
7. Normalize only the selected candidate into `frames/<state>/`.

### What varies between variants

Variants vary **motion read and expression**: how far the body travels, how much it bobs, and the posture and expression language that carry the state. Expression is how `waiting` reads differently from `idle`, and it stays inside the Part Manifest, so the anatomy audit still counts it. For `failed`, variants vary only within the sad family — sobbing versus drooping versus turned-away — never toward neutral or happy.

Identity, palette, props, and style never vary here. Identity variance belongs to the concept sheet, before `canonical-base` is approved. A "variant" that changes the crown cue is not a variant, it is a different Pet.

### Choosing without a human

Quick and Full Automation draw one variant per state, so their judgement happens against the character bible rather than against a spread. Rank by this ladder, in order, and stop at the first level that separates the candidates:

1. **Pre-screen status.** A `fail` is not choosable, whatever else it has going for it.
2. **The identity tests** from [identity-blend.md](identity-blend.md): naming, silhouette, heart. Applied to a state variant these ask whether the Pet is still nameable in motion.
3. **Footprint consistency** against `idle` or `sources/canonical-base.png`, measured as [qa-rubric.md](qa-rubric.md) § Layout QA measures it — the cleaned visible component, not raw alpha bounds.

Write the ranking and the deciding level into the decision record in `qa/approvals.json`. A choice with no stated reason cannot be reviewed after the fact, which defeats the point of keeping the packets at all.

A variant that fails pre-screen is regenerated at most **twice** — the same limit anatomy repair uses. After that, stop and report the state as a character-bible or prompt problem rather than promoting a third attempt or the least-bad frame.

The review page is still rendered when the agent decides. Nothing waits on it, but it makes the build reviewable later and costs no provider call.

Exception for directional rows: create and approve `running-right` first. Then create `running-left` as a deterministic horizontal flip of the approved `running-right` normalized frames and render it as a single candidate such as `running-left-from-right-flip`. Studio asks the human to approve that candidate; Quick and Full Automation record the agent decision. Do not independently generate `running-left` variants unless the human explicitly asks for asymmetric directional art.

A broad "go", "continue", or "looks good" should be treated as permission to generate or continue reviewing candidates, not as approval to promote a candidate. Approval must name the candidate id or clearly choose one of the shown options. It is not a grant of full automation either: that takes an explicit statement about who makes the decisions.

Do not present code-only affine transforms, CSS/canvas animations, or mechanically distorted copies of the canonical base as final sprite-action candidates unless the human explicitly asks for deterministic prototypes. Exception: `running-left` is normally a deterministic horizontal flip of the approved `running-right` source frames for directional consistency. Code may create temporary previews, but active review candidates should be generated imagery except for that mirrored left row. Use code after generation for slicing, chroma-key removal, alpha cleanup, `192x208` normalization, validation, export, and HTML rendering.

## Candidate Packets

Every image generation must return enough context for the parent agent to pre-screen before asking the human. Store candidate packets under:

```text
sources/candidates/<candidate-id>/
  candidate.png
  contact-sheet.png
  candidate-context.json
  prompt.md
  inputs.json
qa/<sprite-action>-review.html
```

`candidate-context.json` must include:

```json
{
  "candidate_id": "waiting-03-a",
  "target": {
    "kind": "sprite-action",
    "state": "waiting",
    "variant": "a",
    "destination": "frames/waiting/"
  },
  "generated_file": "sources/candidates/waiting-a/contact-sheet.png",
  "prompt_file": "sources/candidates/waiting-03-a/prompt.md",
  "prompt_text": "Create the waiting action for...",
  "input_images": [
    {
      "path": "sources/canonical-base.png",
      "role": "identity lock"
    }
  ],
  "identity_invariants": [
    "same silhouette",
    "same face landmarks",
    "same palette",
    "same required props"
  ],
  "state_intent": "expectant asking posture, distinct from idle",
  "variant_intent": "subtle polite lean",
  "known_risks": [
    "cords may drift",
    "heart shape may deform"
  ],
  "agent_pre_screen": {
    "status": "pass",
    "checks": {
      "identity": "pass",
      "layout": "pass",
      "alpha_edges": "pass",
      "state_semantics": "pass",
      "prompt_compliance": "pass"
    },
    "notes": "Looks consistent enough to ask for human approval."
  },
  "human_review": {
    "status": "pending",
    "question": "Choose one waiting variant for frames/waiting/: waiting-a, waiting-b, or waiting-c."
  }
}
```

If a candidate fails pre-screening, set `agent_pre_screen.status` to `fail`, write short failure notes, and do not ask the human unless the failure is subtle and the human explicitly wants to compare variants.

### Concept Sheet Packets

A concept sheet is one image holding many options, so its packet carries per-cell data the per-action shape has nowhere to put. Same envelope, three additions — `grid`, `cells`, and `identity_locks`:

```json
{
  "candidate_id": "concept-sheet-01",
  "target": {
    "kind": "concept-sheet",
    "destination": "sources/candidates/concept-sheet-01/cells/"
  },
  "generated_file": "sources/candidates/concept-sheet-01/candidate.png",
  "grid": {
    "columns": 3,
    "rows": 2,
    "cell_count": 6,
    "aspect_ratio": "3:2"
  },
  "identity_locks": [
    { "cell_id": "cell-01", "text": "Broad woven straw brim, messy black crest, tiny stitch scar below the left eye..." },
    { "cell_id": "cell-02", "text": "Three broad rounded moss crest spikes, one thick dark-green crown band..." }
  ],
  "agent_pre_screen": {
    "status": "pass",
    "cells": [
      {
        "cell_id": "cell-01",
        "status": "pass",
        "checks": { "identity": "pass", "house_form": "pass", "containment": "pass", "scale": "pass" },
        "notes": "Names in under two seconds at thumbnail scale."
      },
      {
        "cell_id": "cell-02",
        "status": "fail",
        "checks": { "identity": "pass", "house_form": "fail", "containment": "pass", "scale": "pass" },
        "notes": "Heart drifted off centre and reads as a badge. Not choosable."
      }
    ]
  },
  "human_review": {
    "status": "pending",
    "question": "Choose one or more cells by id from the concept sheet: cell-01, cell-03, cell-04, cell-05, cell-06."
  }
}
```

The rolled-up `agent_pre_screen.status` is `pass` when **3 or more cells pass**, and `fail` below that — a sheet with two usable options is not worth a human's attention, so redraw it instead. `grid` is what `crop_gallery_cells.py` reads to cut the cells, so it must describe the grid that was actually requested. `identity_locks` is machine-readable so the review page can put each lock beside its overlay number without parsing `prompt.md`; the prose prompt stays the source of truth in `prompt.md`.

## Human-In-The-Loop Review

Apply human approval according to the active workflow profile:

1. Character bible approval before base generation when the brief is ambiguous.
2. Concept sheet cell choice, when the brainstorm route fired. Conditional — it never replaces the gate below.
3. Canonical base variant choice before generating state frames.
4. Studio: per-action variant choice before writing each state to `frames/`. Quick and Full Automation let the agent promote one pre-screened state candidate and record why.
5. Studio: repair approval when a regenerated frame changes expression, pose, prop placement, or silhouette. Quick and Full Automation let the agent decide within the two-pass limit.
6. Final contact-sheet approval before export, install, or delivery when the user is available.

Full Automation also moves gates 1 and 3 to the agent. **Gate 2 and gate 6 never move**: a concept sheet exists so a human can compare identities, and the final audit approves one exact set of pixels before anyone receives them. Export enforces gate 6 in code, so an automated build ends there and waits regardless of what any prompt said.

When asking for approval, render and show an HTML review page:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/render_candidate_review_html.py" /absolute/path/PetName.pet \
  --action waiting \
  --output /absolute/path/PetName.pet/qa/waiting-review.html
```

The HTML page must include:

- One card per passing candidate variant.
- Moving sprite preview for animation states. Use an existing `animated-preview.webp`/`.gif`, or build one from `contact-sheet.png` before asking the human. Contact sheets may appear as supporting artifacts, but must not be the only visual for animation-state approval.
- Exact prompt text and prompt file path.
- Pre-screen status and checks.
- Preserved identity traits and known risks.
- A **Choose** button that copies `I choose <candidate-id> for <sprite-action>.`
- A **Copy Prompt** button that copies the exact prompt.

When asking for approval, link the HTML page and include a compact context summary:

```text
Sprite action: waiting
Options: waiting-a, waiting-b, waiting-c
Review page: qa/waiting-review.html
Target: frames/waiting/
Agent pre-screen: pass
Prompt for waiting-a: Create the waiting action for the Geist Pet...
Preserved: silhouette, face, blue hood, orange heart, cords
Risks to inspect: cord length, heart shape, whether the pose reads as waiting
Decision needed: choose one candidate id, reject all, or request a specific repair
```

Only approved candidates may be normalized into `frames/` or promoted as `sources/canonical-base.png`. The human must respond with a chosen candidate id; clicking the HTML button alone is a convenience for copying the choice back to Codex.

## Frame Creation

Generate high resolution first when useful, but only normalized `192x208` alpha PNGs go into `frames/`.

Two modes draw the art. **Built-in Image Generation** is the default: use `$imagegen` / the built-in capability directly. **External Image Provider** takes over when the bundle holds `imagegen.json`, and `scripts/generate_candidates.py` makes the calls and writes the packet. Read [image-providers.md](image-providers.md) before using that mode. Both modes feed the same approval gates.

Attach the canonical base and any relevant references to every frame or state batch. For a derived Pet, keep the house-style reference attached as well, and restate the two or three highest-ranked identity cues in the prompt by their physical description — those are the cues an animation state is most likely to lose. Each generation returns a candidate packet, not a finished source frame. Prompts should be concise and state-specific:

```text
Create variant A for the Geist Pet "Rainy Geist" in the `waiting` sprite action.
Preserve the exact character bible: blue hood, white face, black dot eyes,
small smile, orange heart, white cords, scalloped cloak. Transparent background.
Create all 6 frames for this state as separate alpha PNG frames or a review contact sheet.
192x208 composition per frame, full body inside safe padding, no shadow, no detached symbols.
Motion read: subtle polite lean and breathing bob, expectant asking posture, distinct from idle, same scale and baseline.
```

When transparent alpha is not reliable from the image generator, prompt for a flat chroma-key background and remove it only after the candidate is selected or when a clean preview is needed. Do not let chroma residue enter `frames/`.

When creating multiple variants, change only motion and expression intent, never identity. Example variant prompts:

```text
Variant A: subtle polite lean, smallest motion, calm waiting.
Variant B: more expectant bob, slight side-to-side shift, still restrained.
Variant C: expressive anticipation, gentle upward bounce, no extra symbols.
```

## State Semantics

Every state animates this Pet's signature, not just its position. Across each state's frames the face (eyes, mouth) and at least one other body part (arm nubs, crown cue, prop, palette accents) must visibly move in a way that fits both the state and the Pet's personality — a state carried by body translation alone is unfinished art, and a state whose expression never changes is a pre-screen reject. Every state also loops in the app, so motion must be smooth and continuous with the last frame flowing back into the first.

- `idle`: subtle breathing, blink, or tiny body bob, with the face alive — slow blinks, a soft mouth, a gentle sway of the crown cue or prop. Not static, not busy.
- `running-right`: moving/gliding to the right, leaning into the glide with eager eyes and trailing body shapes. It is not literal running; do not use legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics.
- `running-left`: horizontal mirror of the approved `running-right` frames by default, so the left and right directional rows are the same sprite cycle flipped. It is not literal running; do not use legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics. Generate independent `running-left` art only if the human explicitly requests asymmetric directional art.
- `waving`: greeting gesture using the body and a raised arm nub, with a bright happy face. No wave marks.
- `jumping`: vertical motion through body position with squash on the way down and stretch on the way up, eyes and mouth reacting to the arc. No floor marks or shadows.
- `failed`: sad, disappointed, deflated or discouraged in **every** frame and nothing else — drooping arm nubs, downturned or flat mouth, sad or downcast eyes, a slightly sagged body. No smile, grin, cheerful eyes, wave, bounce, sparkle, celebration, or any happy or neutral read in any frame. One cheerful frame breaks the whole row.
- `waiting`: asks for approval, help, or user input — expectant lean, questioning eyes, mouth open as if asking.
- `running`: active task work, processing, thinking, scanning, typing, or focused effort, with a concentrated face and busy arm nubs. Not foot-running.
- `review`: focused inspection, reading, leaning, or thinking — narrowed studying eyes, a tilted or leaning body, the prop or crown cue caught up in the scrutiny.

## Repair Loop

Repair the smallest failing unit:

1. Read `qa/validation.json` and visual QA notes.
2. Identify the failed frame or state.
3. Regenerate or edit only that frame/state as a candidate packet using the canonical base and character bible.
4. In Studio, pre-screen at least 2 repair variants when visible art changes and ask the human to choose one. In Quick or Full Automation, pre-screen one and choose it by the ladder, inside the same 2-pass limit.
5. Normalize the selected repair into `frames/`.
6. Re-run validation and export.

Regenerate the canonical base only when many states fail for the same identity reason.
