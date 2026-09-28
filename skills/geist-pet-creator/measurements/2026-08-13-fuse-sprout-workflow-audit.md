# Fuse Sprout: what the pipeline cost, and where the waste lives

One derived Pet, built end to end on 2026-08-12/13 under full automation with
`openai/gpt-image-2`. Concept sheet → cell choice → canonical base → nine states →
audit → export. It shipped: 57 cells, 0 hard errors, post-export digest matching source.

This reads the build against the module that owns each defect, so a fix lands where the
rule lives rather than in one run's `--extra-prompt`.

## The map

Six modules are imported and never run. They are the contract.

| Module | Owns | Imported by |
| --- | --- | --- |
| `geist_grid` | the atlas contract; `FrameGrid` answers which file is frame N | generate, audit, validate, export, registration |
| `geist_pixels` | alpha primitives and the alpha threshold | generate, audit, validate, export, registration, eval |
| `geist_manifest` | reads the **Part Manifest**, renders it into prompts | generate, audit |
| `geist_house` | the **house form** as prompt text; `FRAMING`, `LEGLESS_MOTION`, `FLAT_FIELD`, `MOTION_BUDGET`, concept-sheet grid | generate, crop_gallery_cells, registration, eval |
| `geist_registration` | how big the Pet is and where it sits; ruler, `state_scale`, `placement` | generate, audit |
| `geist_spend` | the ledger: line schema, append, rollup | generate, spend_report |

`generate_candidates.py` is the only executable that spends money, and the only one
importing all six. Everything else reads what it produced. That is a good shape — it means
every cost question has one place to look, and every one of the findings below is a
change to a module rather than to a caller.

## What it cost

**$2.14 total.** `fuse-sprout` $1.99 across 81 calls, `block-world-concepts` $0.15 across 2.
49 frames drawn and kept, 8 mirrored free, 86 images drawn.

Cost by cause, against the $1.22 of kept art:

| Cause | Calls | Cost | Avoidable |
| --- | ---: | ---: | --- |
| Frame size creep → 3 state redraws | 14 | $0.33 | **yes, and free to fix** |
| Face-glyph shape drift → `failed` redrawn | 8 | $0.18 | yes |
| Chroma key failing on a same-hue Pet → `review` redrawn | 6 | $0.14 | yes |
| Doomed transparency attempts on canonical-base | 3 | $0.08 | yes |
| Discarded concept sheet v1 | 1 | $0.09 | partly — a brainstorm is allowed one miss |
| Two canonical-base variants not chosen | 2 | $0.10 | **no — this is the cheap variance** |
| **Total avoidable** | | **~$0.82** | **38% of the build** |

Four of nine states were right on the first draw: `running-right`, `waving`, `jumping`,
and `waiting`. Every one of the four failures had a cause a second variant would have
reproduced identically — which is fresh evidence for the skill's own one-variant-per-state
rule, not against it.

## Finding 1 — `MOTION_BUDGET` has no twin, and size drifts because of it

`geist_house.MOTION_BUDGET` declares, per state, how far a body may leave the anchor, and
defaults an unknown state to `STILL` on the stated grounds that it "should hold still and
be visibly wrong, not wander and look like art."

**There is no `SIZE_BUDGET`.** Nothing declares which states may change size, so nothing
can tell a breathing pulse from a defect. Measured spread within a state on this build:

| State | Area spread as drawn | Should be |
| --- | ---: | --- |
| `review` | 1.46x | pinned |
| `idle` | 1.41x | pinned |
| `waiting` | 1.37x | pinned |
| `running` | 1.32x | pinned |
| `failed` | 1.50x | free — deflation is the pose |
| `jumping` | 1.21x | free — squash and stretch is the pose |

The mechanism is `generate_candidates.py` drawing one frame per call with the previous
frame attached as a reference: size ratchets along the chain, and frames 00-01 come back
smallest every time.

`geist_registration.state_scale` cannot correct it and should not — it applies one shared
scale per state, deliberately, because for `failed` and `jumping` a size change is the art.

**Three paid redraws were spent trying to fix this with prompt text and bought nothing.**
A SIZE LOCK in `--extra-prompt` appeared to work once (`idle` 1.41x → 1.14x); the next
state came back at **0.54x** and was killed by pre-flight, and a third landed at 1.46x.
It is noise, not control.

What worked was deterministic, free, and took one pass: scale each frame to the state's
median area, re-anchored on bbox centre horizontally and base line vertically — the same
anchor `geist_registration` already uses. All five pinned states landed at 1.01-1.03x.

**Recommendation.** Add `SIZE_BUDGET` to `geist_house` as `MOTION_BUDGET`'s twin, listing
the states where size change is the pose (`failed`, `jumping`) and defaulting everything
else to pinned. Have `geist_registration` normalise per-frame area for pinned states as
part of the pass it already runs. Saves ~$0.33 per Pet and costs nothing to execute.

## Finding 2 — pre-flight measures against frame 0, which the codebase elsewhere calls wrong

`AREA_TOLERANCE = 0.35`, compared against **frame 0**, and `PREFLIGHT_FRAMES = 2` means a
non-fatal problem only aborts inside the first two frames. A fatal one stops anywhere,
which is why `review` halted at frame 5 when its background would not key.

Two consequences on this build:

- `review` drifted to 1.46x across frames 2-5 and nothing stopped it, because the check
  had already gone quiet after frame 1.
- `waiting`'s repair was killed at frame 1 for being 0.54x frame 0 — the check working,
  and it saved four frames of spend. Pre-flight is worth keeping; it is scoped too narrowly.

Frame 0 as the ruler also contradicts the principle `geist_registration` states in its own
docstring: *"A frame 0 is a pose; a median over the state is the Pet."* The generator
applies the state median when it registers, then judges drift against frame 0.

**Recommendation.** Compare each frame's area to the running median of the frames drawn so
far, not to frame 0, and keep the check live for the whole state rather than the first two
frames. Measuring is free; only drawing costs.

## Finding 3 — the chroma key is a constant, and this Pet was the same colour as it

`generate_candidates.CHROMA_KEY = (0, 255, 0)`, hardcoded. Fuse Sprout's body is `#9FC351`.
Five of six `review` frames keyed; the sixth came back opaque and cost the state.

Nothing consults the canonical base before choosing the backdrop, so a green Pet, a
magenta Pet, or a blue Pet each carry a silent tax that fires unpredictably. When it fires
it is a total loss.

**Recommendation.** Derive the key from `sources/canonical-base.png` — pick the keying hue
furthest from the Pet's palette, and record it in the candidate packet's provenance
alongside `alpha_path`. Magenta for a green Pet, green for a magenta one. One function,
probably in `geist_pixels`, consulted once per bundle.

## Finding 4 — the Part Manifest counts parts but cannot describe them

This is the structural one.

`failed`'s first draw replaced the connected face glyph with separate eyes and a detached
frown, and dropped the mouth tab across all 8 frames — drift on the rank-2 identity cue.

**It satisfied the Part Manifest completely.** The manifest says `mouth shape | 1`, and the
drifted art had exactly one mouth. `geist_manifest` renders counts into prompts, and the
audit checks counts, so a part that keeps its count while changing its shape is invisible
to both.

The skill defines anatomy drift as "a part missing, a part duplicated, or a part crossing
the cell line." **Shape drift is a fourth kind, and nothing looks for it.** On this build it
was caught by eye and cost $0.18 to fix; on a Pet whose reviewer is less familiar with the
source it would ship.

**Recommendation.** Give the Part Manifest a shape column, or give `character-bible.md` a
glyph-lock block that `geist_manifest` renders verbatim into every frame prompt. Counting
is necessary and not sufficient. Worth noting the mechanical check that *did* work here:
counting connected ink components per frame found 1 glyph in all 57 cells — the same
technique would have flagged the drifted row, which had 3.

## Finding 5 — the digest is stamped before the repairs that invalidate it

`audit_spritesheet.py` builds its payload including `atlas_digest(atlas)`, and its
`--repair` path calls `register_states` afterwards, which rewrote all 57 frames on this
build. The recorded digest therefore named pixels that no longer existed.

Cost: no money, and a false export refusal plus a re-approval that had to be justified with
a before/after fingerprint to show the human's approval still covered the same art. That is
the expensive kind of confusion — it puts a gate's integrity in question.

**Recommendation.** Compute the digest last, after every repair pass, or re-stamp it. One
line, and it removes a failure that looks like tampering.

## Finding 6 — `approvals.json` has two shapes and one reader

`SKILL.md` says to "record approvals in `qa/approvals.json` with candidate id, approved file
path, target destination, approver note, and timestamp." `export_geist_pet.audit_approval`
requires a **top-level JSON array** whose entries carry `decision: "approved"` — a field the
documented list does not mention.

The reader's error message is excellent and diagnosed it immediately. The schema is still
only discoverable by reading the reader.

**Recommendation.** One writer function, in a module both sides import, so the gate's
schema has a single definition. Failing that, document `decision` in `contract.md`.

## What worked, and should not be traded away

- **`running-left` as a free mirror.** 8 frames, $0.00, verified pixel-identical to a flip
  of the approved right row. This is the best ratio in the pipeline.
- **Three canonical-base variants for $0.175.** That is the right place for variance: it
  decided what all 57 later frames were counted against. Keep the standing exception.
- **One variant per animation state.** Vindicated. The three states that failed on size
  shared a mechanism no sibling variant would have escaped.
- **Pre-flight aborting a bad repair at frame 1.** Saved four frames on `waiting`.
- **`ALPHA_PATHS`.** The sprite states never paid the doomed transparency call. The $0.08
  that was paid came from a local runner in `pet-design/tools/` that predates it.

## One process note outside the skill

`pet-design/tools/build_demon_slayer_concept_gallery.py` and the
`build_canonical_base_candidates.py` written during this build are now duplicate spend paths.
The skill's `generate_candidates.py --action concept-sheet|canonical-base` covers both. The
local copies carry their own `KNOWN_MODELS` — one of which had already drifted wrong and
deleted a working model — and they write no ledger lines, which is why $0.32 of this build
had to be back-filled by hand. Retire them.
