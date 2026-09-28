# What Rework Cost, And What Closed It

Fifteen defects, found across three measured builds, each now closed in code. Read this when a build comes in over budget, when a defect looks familiar, or before adding a rule to SKILL.md that the model will never see.

Every one of them was **a number with no owner, or with two**. That is the diagnostic worth carrying: when a build misbehaves, ask which module owns the number it got wrong. If the answer is "two of them" or "none", the fix is a module, not a caller — and a rule that lives only in prose is a rule with no owner at all.

## The first build: $3.18, and 55% of it rework

Measured 2026-08-12. 109 frames drawn to keep 50. None of it came from model quality or bad luck; every dollar came from drawing frames that were never going to be kept.

| The rework | Owner that closes it |
| --- | --- |
| Every frame drawn twice, chasing alpha the model cannot return | `ALPHA_PATHS` — the model's capability decides the request |
| Frames clipping the cell edge | motion headroom, reserved in the cell transform |
| A directional state drawing legs across all eight frames | `LEGLESS_MOTION` in the frame prompt |
| A frame returning an unkeyed panel | `FLAT_FIELD` in the frame prompt |
| Five to eight frames of a defect visible in frame 0 | pre-flight stops the state at two |
| Two extra variants of a state that shared one prompt defect | one variant per state |

Three more from the same audit cost money in every build, not only that one:

| The rework | Owner that closes it |
| --- | --- |
| `running-left` drawn through the provider, when the rule already said "flip `running-right`" | the flip ships; `--independent-left` is the opt-in |
| Correct `jumping` and directional frames queued for **paid** redraw on an advisory suspicion score | only a hard error or a stray fragment buys art; suspicion goes to `flagged_for_review` |
| A whole state redrawn for cell bleed a rescale would fix | `refit_state` rescales the row by one shared factor from its union bbox |

## FarWatcher and FuseSprout: six more

2026-08-12 and 2026-08-13. Both shipped; both spent about 37% of their budget on art they threw away.

| The rework | Cost | Owner that closes it |
| --- | ---: | --- |
| A body that ratchets bigger frame by frame, and three paid redraws fighting it with prompt text | $0.33 | `geist_house.SIZE_BUDGET`, enforced free by `geist_registration.normalise_size` |
| Detached speed lines pre-flight could not see, drawn across two whole states | $0.29 | `geist_pixels.component_count` in pre-flight, against the canonical base's own count |
| A face glyph that came back in pieces while satisfying the Part Manifest exactly | $0.18 | the Part Manifest's `Shape` column, rendered verbatim into every frame prompt |
| A green Pet keyed off a green backdrop | $0.14 | `choose_chroma_key` reads the base and picks the backdrop furthest from it |
| Frames drawn, billed, and never written because the run stopped before the state ended | $0.07 | each frame lands on disk as the provider answers, resumable with `--frames` |
| An export refused by a digest stamped before the repair that invalidated it | — | the digest is re-stamped after registration, not only after deterministic repair |

## The two quotes this section has retired

**$1.33** was quoted for years as a clean pass. It is `57 x $0.023349`, and that median is the sum of **two** billed calls per frame — the discarded opaque draw and the chroma draw that was kept. A build landing on $1.33 was matching the waste, not proving itself healthy.

**$0.57** replaced it on 2026-08-12, by halving that median to remove the double draw. Halving was right in principle and wrong in fact: the per-call price of a single frame is simply higher than $0.0117. Two independent ledgers then landed at $0.0227 and $0.0246.

That $1.33 sits close to the honest single-call figure is a coincidence of two errors, not a vindication.

## Full write-ups

- [../measurements/2026-08-12-pet-cost-root-cause.md](../measurements/2026-08-12-pet-cost-root-cause.md) — the $3.18 build, defect by defect
- [../measurements/2026-08-12-far-watcher-build.md](../measurements/2026-08-12-far-watcher-build.md) — the first build measured end to end against a real ledger
- [../measurements/2026-08-13-fuse-sprout-workflow-audit.md](../measurements/2026-08-13-fuse-sprout-workflow-audit.md) — the same, read against the module owning each defect
