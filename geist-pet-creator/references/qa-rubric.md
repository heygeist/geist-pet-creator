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

### Derived Pets

A derived Pet is judged against both of its locks. Read [identity-blend.md](identity-blend.md) for the house form and the cue budget; this is how the result gets checked.

Reject a candidate that fails either direction:

- **Franchise copy** — the source's own outline color instead of Sky, original body proportions kept whole, a full figure with legs, the face drawn in the source's rendering style, or a Mango heart that is missing, tacked on, or floating outside the silhouette.
- **Generic blob** — the source cannot be named from a `192x208` thumbnail, the cues collapsed into one hat and one color, several gallery cells are interchangeable, or identity survives only at full resolution.

Three tests settle it, and all three run before the human sees the candidate:

- **Naming test** — at `192x208`, someone who knows the source names it in about two seconds.
- **Silhouette test** — filled solid black, the crown cue and prop shape still say who it is.
- **Heart test** — with the Mango heart and Sky outline removed, what remains must not look like official art from the source.

Also reject a derived candidate when a cue listed in the `## Identity Blend` table is absent without the pose hiding it, when a cue recorded as dropped has returned, when a second prop has appeared, or when a source name rather than a physical description was used in the prompt.

## Candidate Pre-Screen QA

Before asking the human to review a generated candidate, the agent must check:

- Generation source: new visible canonical-base or sprite-action art came from image generation, not code-only transforms, unless the human explicitly requested deterministic prototypes.
- Anatomy: every part in the Part Manifest appears within its count range, on the stated side.
- Target clarity: the candidate matches the requested base, state, frame, or repair target.
- Identity: required traits from `character-bible.md` are visible and stable.
- House form (derived Pets): every house-form invariant holds — legless rounded body, single Sky exterior outline, Cream body area, dot eyes, tiny mouth, exactly one centered Mango heart inside the silhouette, flat fills, attached props, no floor or shadow.
- Identity read (derived Pets): the ranked cues in the `## Identity Blend` table are present, and the candidate passes the naming, silhouette, and heart tests.
- Blend balance (derived Pets): the candidate is neither a franchise copy nor a generic blob.
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
- A derived Pet has no `## Identity Blend` table in `character-bible.md`, or the packet's `inputs.json` does not carry both the identity reference and the house-style reference.
- A concept gallery is shown with any cell unscreened. A gallery is one candidate; it passes only if every cell passes.

## Anatomy QA

Anatomy drift is a frame disagreeing with the Part Manifest. It comes in three shapes:

- **Missing part** — a part the manifest requires is absent, and the pose does not hide it.
- **Duplicated part** — a part appears more times than its high bound. A hand, wing, or arm drawn twice is the common case.
- **Cell bleed** — visible pixels reach a cell edge, so part of the Pet crosses into the next cell.

Geometry checks stay silent on the first two. A frame with a missing wing has the correct size, one component, correct padding, and clean alpha. So anatomy is judged by looking at every frame, against the Part Manifest in `character-bible.md`.

Audit every one of the 57 artwork cells. Record a verdict for each in `qa/final-audit.json`, then confirm none is missing:

```bash
python "$SKILL_DIR/scripts/audit_spritesheet.py" /absolute/path/PetName.pet --verify-verdicts
```

### Reading the audit evidence

`audit_spritesheet.py` measures each frame against its state's anchor frame and ranks the state by suspicion. Suspicion points attention. A frame scoring zero has only been found unremarkable by six measurements, which is a different thing from correct.

Two limits are worth holding in mind while reading a report:

- The anchor frame is compared against itself, so its score is structurally zero and says nothing about its artwork. The anchor is as likely to be the wrong frame as any other.
- A defect shared by every frame of a state moves no relative signal at all. Only the Part Manifest catches that one.

Hovering a frame on `qa/final-audit.html` shows what it gained (red) and lost (blue) against its anchor. A part that vanished between frames shows up as a solid blue mass; a part that appeared shows up as a solid red one.

### Repairing anatomy drift

Repair runs automatically and splits by whether the pixels already exist:

- **Deterministic repair** moves or clears existing pixels: transparent RGB residue, detached fragments under 2% of the body, and a body shifted back inside safe padding. It writes in place after copying the original to `sources/raw/repair-backups/`.
- **Generative repair** creates pixels, because a missing wing cannot be recovered from a file that lacks it. It produces a candidate packet and waits for the human to approve it, exactly like any other generated art.

A frame gets at most 2 repair passes. A frame that fails twice has a prompt problem or a Part Manifest problem, so fix the character bible or the prompt rather than the frame.

Keep the flagged-frame count visible even after repairs succeed. A Pet flagging 15 of 57 frames is telling you the identity lock is weak, and repairing 15 frames hides that.

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
