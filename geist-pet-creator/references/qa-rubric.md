# QA Rubric

Use this rubric before accepting a Pet source bundle or exported atlas.

## Identity QA

Reject frames where any of these drift:

- Species or body type
- Silhouette or proportions
- Face area, eye shape, eye spacing, mouth placement
- Palette, material, line quality, or rendering style
- Required props, markings, accessories, cords, clothing, or side-specific details

The same Pet should be recognizable if frames are shuffled out of order.

## Candidate Pre-Screen QA

Before asking the human to review a generated candidate, the agent must check:

- Generation source: new visible canonical-base or sprite-action art came from image generation, not code-only transforms, unless the human explicitly requested deterministic prototypes.
- Target clarity: the candidate matches the requested base, state, frame, or repair target.
- Identity: required traits from `character-bible.md` are visible and stable.
- Layout: whole Pet is inside the frame with safe padding and no copied guide marks.
- Alpha or extraction readiness: background can be made transparent cleanly; no obvious fringe or residue.
- State semantics: pose reads as the requested Geist state.
- Prompt compliance: no forbidden props, symbols, text, shadows, or detached effects.

Reject clear failures before human review. Escalate borderline subjective choices with explicit risks instead of hiding uncertainty.

Human review should receive multiple candidate variants for the sprite action, each with a preview image/contact sheet, exact prompt, candidate id, and short context summary. Do not ask the human to approve only one candidate unless the task is a deterministic cleanup of already-approved art.

Prefer an HTML review page at `qa/<sprite-action>-review.html` for every approval gate. For animation states, verify the page renders each candidate as a moving sprite preview, not only as a static contact sheet. Verify the page has exact prompt text, a **Choose** button, and a **Copy Prompt** button for each passing candidate before asking for human validation.

Reject the review packet before showing it to the human if:

- Fewer than 3 variants are provided for a new sprite action and the human did not request a different count.
- The exact prompt for each variant is missing.
- Candidate ids are ambiguous or cannot be mapped to the destination action.
- The approval question does not require choosing a specific candidate id.
- The HTML review page is missing for a generated-art approval gate, unless the human explicitly requested plain-text review.
- The review page does not render an animation-state candidate as a moving sprite preview.
- The active candidates are only scripted transforms of approved art and the human expected image-generated sprite art.

## Layout QA

Reject frames with:

- Non-`192x208` normalized frame size
- Cropped body parts or effects
- Sprite touching the cell edge without explicit approval
- Large baseline jumps not required by the state
- Scale popping between adjacent frames
- Multiple separated sprite components unless an attached prop is intentionally part of the Pet

When judging visible sprite size, measure the true visible sprite rather than raw alpha bounds:

- Remove or ignore low-alpha residue before measuring.
- Ignore thin guide/ruler components.
- Ignore tiny specks and isolated cleanup pixels.
- Measure the largest real visible sprite component after that cleanup.

Use this cleaned component measurement for scale comparisons, crop checks, and footprint repairs. Raw alpha bounds can be fooled by guide marks or residue and must not be the only scale signal.

## Alpha And Edge QA

Reject frames with:

- No alpha channel
- White, black, checkerboard, or chroma-key background left in the frame
- Green/cyan fringe on semi-transparent or boundary pixels
- Transparent pixels retaining colored RGB residue after normalization
- Soft shadows, glows, smears, or anti-aliased background haze

## Motion QA

Inspect previews after export:

- First and last frames should loop without a jarring jump.
- `idle`, `waiting`, `running`, and `review` must show visible but restrained motion.
- Directional rows must face and travel the correct direction. By default, `running-left` should be a horizontal mirror of the approved `running-right` source frames; reject independently generated `running-left` art unless the human explicitly requested asymmetric directional art.
- `running-right` and `running-left` must read as lateral movement/gliding, not leg-running, walking, feet, or foot-step poses.
- `running` must read as task work, not jogging or sprinting.
- `jumping` may move vertically but must not scale-drift.

## Repair Notes

Write repair notes as direct frame or state instructions:

```text
waiting/03.png: face drifted wider and heart changed shape; regenerate with canonical-base.png and preserve orange heart shape.
running-right: frames 04-07 touch right edge; reduce stride width or recenter without changing scale.
```
