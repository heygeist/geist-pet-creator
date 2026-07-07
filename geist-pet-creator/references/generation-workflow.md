# Generation Workflow

Use this guide before creating new Pet art.

## Pet Brief

Capture:

- Pet name and one-sentence description
- Personality and state behavior
- Visual references
- Required features that must never drift
- Forbidden changes
- Target style and readability constraints

## Character Bible

Write `character-bible.md` before generating frames. Include:

- Silhouette: body shape, proportions, scale, anchor point
- Palette: named colors and materials
- Face landmarks: eye shape, eye spacing, mouth placement, face area
- Props and accessories: side, shape, colors, attachment points
- Motion personality: how this Pet idles, asks, works, fails, and reviews
- Avoidances: marks, effects, styles, objects, or expressions that would break identity

## Canonical Base

Create `sources/canonical-base.png` as a full-body alpha or clean-background reference. It is not enough for the base to look nice; it must be simple enough to preserve across all animation states at `192x208`.

Generate multiple base variants as candidate packets first, using image generation for new visible art. The agent must pre-screen each candidate, show the passing options with their exact prompts, and ask the human to choose one candidate id before copying it to `sources/canonical-base.png`.

## Sprite Action Variant Review

Every sprite action/state requires its own human validation before source frames are written. The required sprite actions are:

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

1. Generate at least 3 variants with the built-in image generation capability unless the human specifies another count.
2. Store each variant as its own candidate packet or as a clearly named variant inside an action candidate set.
3. Include the exact generation prompt for every variant in `prompt.md`.
4. Pre-screen each variant and reject obvious failures before human review.
5. Render an HTML review page with candidate id, moving sprite preview, prompt, preserved identity traits, risks, a **Choose** button, and a **Copy Prompt** button for every passing variant. Contact sheets may appear as supporting artifacts, but animation-state review must show motion.
6. Wait for the human to choose one candidate id for that action.
7. Normalize only the selected candidate into `frames/<state>/`.

Exception for directional rows: create and approve `running-right` first. Then create `running-left` as a deterministic horizontal flip of the approved `running-right` normalized frames, render it as a single candidate such as `running-left-from-right-flip`, and ask the human to approve that exact mirrored candidate before writing `frames/running-left/`. Do not independently generate `running-left` variants unless the human explicitly asks for asymmetric directional art.

A broad "go", "continue", or "looks good" should be treated as permission to generate or continue reviewing candidates, not as approval to promote a candidate. Approval must name the candidate id or clearly choose one of the shown options.

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

## Human-In-The-Loop Review

Use human approval at these gates:

1. Character bible approval before base generation when the brief is ambiguous.
2. Canonical base variant choice before generating state frames.
3. Per-action variant choice before writing each state to `frames/`.
4. Repair approval when a regenerated frame changes expression, pose, prop placement, or silhouette.
5. Final contact-sheet approval before export, install, or delivery when the user is available.

When asking for approval, render and show an HTML review page:

```bash
python "$SKILL_DIR/scripts/render_candidate_review_html.py" /absolute/path/PetName.pet \
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

Use `$imagegen` / the built-in image generation capability for visual generation. Attach the canonical base and any relevant references to every frame or state batch. Each generation returns a candidate packet, not a finished source frame. Prompts should be concise and state-specific:

```text
Create variant A for the Geist Pet "Rainy Geist" in the `waiting` sprite action.
Preserve the exact character bible: blue hood, white face, black dot eyes,
small smile, orange heart, white cords, scalloped cloak. Transparent background.
Create all 6 frames for this state as separate alpha PNG frames or a review contact sheet.
192x208 composition per frame, full body inside safe padding, no shadow, no detached symbols.
Motion read: subtle polite lean and breathing bob, expectant asking posture, distinct from idle, same scale and baseline.
```

When transparent alpha is not reliable from the image generator, prompt for a flat chroma-key background and remove it only after the candidate is selected or when a clean preview is needed. Do not let chroma residue enter `frames/`.

When creating multiple variants, change only motion intent, not identity. Example variant prompts:

```text
Variant A: subtle polite lean, smallest motion, calm waiting.
Variant B: more expectant bob, slight side-to-side shift, still restrained.
Variant C: expressive anticipation, gentle upward bounce, no extra symbols.
```

## State Semantics

- `idle`: subtle breathing, blink, or tiny body bob. Not static, not busy.
- `running-right`: moving/gliding to the right. It is not literal running; do not use legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics.
- `running-left`: horizontal mirror of the approved `running-right` frames by default, so the left and right directional rows are the same sprite cycle flipped. It is not literal running; do not use legs, feet, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics. Generate independent `running-left` art only if the human explicitly requests asymmetric directional art.
- `waving`: greeting gesture using the body or limb, no wave marks.
- `jumping`: vertical motion through body position, no floor marks or shadows.
- `failed`: error or deflated reaction, readable but not noisy.
- `waiting`: asks for approval, help, or user input.
- `running`: active task work, processing, thinking, scanning, typing, or focused effort. Not foot-running.
- `review`: focused inspection, reading, leaning, or thinking.

## Repair Loop

Repair the smallest failing unit:

1. Read `qa/validation.json` and visual QA notes.
2. Identify the failed frame or state.
3. Regenerate or edit only that frame/state as a candidate packet using the canonical base and character bible.
4. Pre-screen at least 2 repair variants when the visible art changes, then ask the human to choose one.
5. Normalize the approved repair into `frames/`.
6. Re-run validation and export.

Regenerate the canonical base only when many states fail for the same identity reason.
