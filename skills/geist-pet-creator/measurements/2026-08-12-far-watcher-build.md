# Far Watcher: one build, measured end to end

A single derived Pet taken from brainstorm to exported spritesheet on
`openai/gpt-image-2`, by an agent under full automation. It is the first build to
confirm § What A Pet Costs against a real ledger, which that section says the
next build owes it. It does not confirm it. It also found three defects the
pipeline could not see, and one the pipeline had already fixed in a module the
agent never found.

## The map

Nine scripts and five modules. What actually matters is which of them owns a
number, because every defect below is a number owned in two places or in none.

```
                     geist_house      geist_grid      geist_manifest
                     (house form,     (atlas          (Part Manifest
                      motion budget)   contract)       -> prompt text)
                          |  |            |  |              |
              +-----------+  +---+    +---+  +----+         |
              |                  |    |           |         |
      geist_registration    generate_candidates   |    audit_spritesheet
      (size + position,      (draws every phase)  |    (57 cells vs manifest)
       ONE ruler per bundle)      |               |         |
              |                   |          export_geist_pet
              +-------------------+----------------+--------+
                                  |
                            geist_spend
                        (the ledger, one line per call)
```

`geist_registration` is the newest and the one this build never used: it is
imported by both the generator and the auditor, and it is the only module that
compares a **state** to the **Pet** rather than to itself.

## What it cost

| Phase | Calls | Cost | Kept |
| --- | ---: | ---: | ---: |
| `--verify-model` | 1 | $0.007 | — |
| concept sheet v1 + v2 | 2 | $0.149 | v2 |
| canonical-base, ad-hoc runner, 3 rounds | 9 | $0.314 | none |
| canonical-base, skill `--action` | 3 | $0.073 | 1 |
| eight drawn states | 69 | $1.562 | 49 frames |
| `running-left` | 0 | $0.000 | 8 frames |
| **total** | **84** | **$2.104** | 57 frames |

**Measured per-call: $0.0227.** The skill quotes ~$0.012. Every frame was a
single call — this is not the double-draw waste already closed — so the quote is
low by 1.9x for this shape. A clean 57-frame pass on this model is about
**$1.11**, not $0.57. Every frame call carries two reference images, the
canonical base and the previous frame, and that is the obvious suspect.

**Rework was $0.76 of $2.10 — 36%.** Not one dollar of it came from model
quality:

| Wasted | Calls | Cost | Cause |
| --- | ---: | ---: | --- |
| `running-right` variant a | 8 | $0.182 | speed lines, a prompt defect |
| `jumping` variant a | 5 | $0.110 | same defect |
| `waving` variant a | 4 | $0.087 | raised arm swapped sides |
| `failed`, killed in flight | 3 | $0.067 | frames only land at state end |
| ad-hoc base runner, 3 rounds | 9 | $0.314 | a second implementation of a phase the skill owns |

## Six enhancements, most expensive first

### 1. Pre-flight is mechanical, and the defect that cost most was semantic

`running-right` frame 0 came back with detached speed lines. Pre-flight passed
it, and 13 frames across two states were drawn and discarded — **$0.29**, the
largest single line of waste here.

Pre-flight checks geometry and alpha. Speed lines break neither. But they are
trivially visible to a check the pipeline can already make: **a detached mark is
an extra connected component.** Count components on frame 0 and compare against
the canonical base. The Pet is one component plus whatever the manifest declares;
2-4 floating streaks are 2-4 more.

That check is free, runs on art already paid for, and would have stopped both
states at frame 1. Add it to `PREFLIGHT_FRAMES` alongside the mechanical checks.

### 2. The cost quote is 1.9x low, and the previous-frame reference is why

Before re-quoting $0.57, measure the reference payload. `eval_providers.py`
already has the harness: draw one state with both references, one with the
canonical base only, and compare cost against identity drift. If the
previous-frame reference is not earning 90% of a frame's price, dropping it
saves roughly **$0.55 per Pet** — more than every other item here combined.

If it *is* earning it, say so in § What A Pet Costs and raise the quote to $1.11.
Either outcome is worth the one measurement. Quoting $0.57 while builds land at
$2.00 makes the budget line useless as a guardrail.

### 3. Frames only land at state end, so an interruption burns everything drawn

Stopping the run to fix the speed-line defect cost 3 paid `failed` frames that
were never written. Writing each frame into the packet as the provider answers
costs nothing and makes an interrupted state resumable with `--frames`.

This is the same argument `geist_spend` already makes for appending a ledger line
the moment a provider answers rather than when a packet lands — a run killed at a
ceiling spends real money. The frames deserve the same treatment as the receipt.

### 4. `geist_registration` exists, and the agent hand-rolled a worse version

The human reported two defects — the character changing size between frames, and
wandering during playback. Both are exactly what `geist_registration` is for. The
agent did not find it and wrote its own normalizer, which was worse in three
specific ways:

| | hand-rolled | `geist_registration` |
| --- | --- | --- |
| ruler | `idle/00`'s bbox | the canonical base, one per bundle |
| size metric | `sqrt(w*h)` of the bbox | alpha area, median across the row |
| vertical anchor | bbox centre | base line |
| motion | offsets invented per state | `MOTION_BUDGET`, declared |

The bbox ruler is pose-sensitive: `waving`'s raised arm inflated its bbox, so
normalizing on it made that state's **body** the smallest on the sheet at 0.894
of the ruler. Running `--repair` afterwards moved it to 0.928 and took base-line
spread to **0px** on every pinned state. The hand-rolled version also invented a
2px idle bob and a 10px jumping hop; the declared budgets are `(0,0)` and
`(0,26)`.

The word "registration" does not appear in SKILL.md. § Validation And Repair
should name `--repair`'s `registered` output and say plainly that size and
position are owned by that module, so the next agent reaches for it instead of a
ruler of its own. **A capability nobody can find gets rebuilt worse.**

### 5. Ad-hoc runners spend money the ledger never sees

`pet-design/tools/build_canonical_candidates.py` and
`build_demon_slayer_concept_gallery.py` call the provider directly and append no
ledger line. They hid **$0.314 of this Pet's cost** — 16% — from
`spend_report.py`, which is the tool whose whole job is answering what a Pet cost.

The skill now covers every phase with `--action`, so both runners are redundant.
Delete them, or route them through `geist_spend.SpendLedger`. A receipt with a
silent 16% gap is worse than no receipt, because it reads as complete.

### 6. Two small ordering traps that cost retries

- **`--fix-transparent-rgb` has to run last.** The audit's write path
  reintroduces residue, so validate → audit → validate is required, and the build
  ran that loop three times before it came back clean. Clear residue inside the
  audit's own write instead.
- **`approvals.json` shape is undocumented.** The exporter wants a top-level
  array with `decision: "approved"`; the agent wrote `{"approvals": [...]}` and
  lost two export attempts to it. The error message was excellent — it named the
  shape it wanted. Put that shape in `contract.md` so it never has to.

## What went right, and should not be traded away

- **`running-left` cost nothing.** 8 of 57 frames for zero calls, and both
  directions are guaranteed the same character.
- **One variant per state held.** Six of nine actions were right first time. The
  three that were not shared one prompt defect, exactly as § One variant per
  animation state predicts — no sibling variant would have solved it.
- **Fixing the prompt in `geist_house` rather than `--extra-prompt` worked.**
  `running` was still queued when the speed-line cause was closed, and it drew
  clean. That is the rule earning its keep in the same session it was applied.
- **The final-audit gate caught nothing, and should stay.** Both defects the
  human found — the black stripe across the cube and the wandering — passed
  validation, passed the anatomy audit with zero hard errors, and passed 57
  written verdicts. A human looked at the sheet and saw both in one pass.
