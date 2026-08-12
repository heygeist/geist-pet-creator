# Concept-sheet smoke test — 2026-08-12

A **smoke test, not the eval.** Two cases against two models, to price a sheet and find out whether
the metrics work before spending on the full six-by-seven run. Raw data:
[`2026-08-12-concept-sheet-smoke.json`](2026-08-12-concept-sheet-smoke.json).

**4 provider calls, $0.1524.** No fallbacks: a sheet asks for opaque paper, so neither the
parameter-drop nor the chroma path ever fires.

```bash
scripts/with_openrouter_key.sh python3 scripts/eval_providers.py \
  --out concept-sheet-eval-smoke \
  --models openai/gpt-image-2 google/gemini-3.1-flash-lite-image \
  --cases order-count-6 cast-derived-12 --max-images 8 --max-cost-usd 0.60
```

## Method

Two cases chosen for the two live unknowns, not for coverage:

| Case | Grid | Tests |
| --- | --- | --- |
| `order-count-6` | 3x2 | Does row-major order hold? Cells separated by an ordered body-hue palette |
| `cast-derived-12` | 4x3 | Does the 12-cell cap survive contact, and what does a big sheet cost? |

A sheet is scored on whether its cells are **comparable** — cell count, containment inside the cell
rect, scale spread, baseline spread, row-major order — because comparability is the only reason to
draw cells in one call rather than separately.

## Results

| Case | Model | Size | Cost | Duration |
| --- | --- | --- | ---: | ---: |
| `order-count-6` | `openai/gpt-image-2` | 1536x1024 | $0.0483 | 48.7s |
| `order-count-6` | `google/gemini-3.1-flash-lite-image` | 1264x848 | $0.0341 | 7.9s |
| `cast-derived-12` | `openai/gpt-image-2` | 1536x1152 | $0.0346 | 54.5s |
| `cast-derived-12` | `google/gemini-3.1-flash-lite-image` | 1200x896 | $0.0355 | 4.1s |

## What it found

**A sheet costs $0.034–$0.048, above the frame band.** The 2026-08-12 provider eval measured
`openai/gpt-image-2` frames at $0.0175–$0.0243. A sheet is roughly **1.5x to 2x a frame** — more
pixels, as expected, but nowhere near proportional to holding twelve mascots. Twelve concepts for
$0.035 is about a fortieth of what twelve separate canonical-base candidates would cost. The full
six-case, seven-model run should land near $1.50, comfortably inside the $6.00 ceiling.

**Cell count held perfectly.** 6 of 6 and 12 of 12 on both models. The 12-cell cap from the grid
table survives contact; nothing here argues for lowering it. Twelve cells on a 1536x1152 canvas
gives 384x384 a cell, which is ample for the naming test.

**Both models honoured `aspect_ratio`.** 3:2 and 4:3 came back as requested by both. Pairing the
grid with an aspect ratio works; it is not being silently dropped.

**Speed differs by 13x, cost by almost nothing.** `gemini-3.1-flash-lite-image` drew a 12-cell sheet
in 4.1s against 54.5s for `gpt-image-2`, for $0.0355 against $0.0346. On frames that model is three
times dearer than the default; on sheets it is the same price and an order of magnitude faster. If
the full run holds this up, the sheet step and the frame step may want different models — which the
per-run `--model` override already allows without repinning the bundle.

## Two defects it found, both in this repo rather than in a model

**The order probe raised three false positives on correct sheets.** It asked which expected hue each
cell was closest to. The palette steps by 40 degrees in places, and models render "magenta" as a
pink near 340 — which is closer to red at 0 than to magenta at 310. Both sheets were visually
correct, in the requested order, and the probe called them broken.

Fixed by testing **rank rather than proximity**: observed hue must rise across the cells the way the
requested palette does. A swap breaks monotonicity; a colour merely rendered warm does not. Both real
sheets now report clean, and a synthetic sheet with two cells swapped is still caught. The cost of
the fix is precision of attribution — the check names the boundary where order breaks, not the exact
pair that swapped.

**Cutting cells on an even grid would have clipped every mascot in a row.** `gpt-image-2` drew its
4x3 sheet with the first row of mascots running to y=245 of a 675-pixel canvas, while even thirds put
the boundary at 225. Cutting there shaves 20 pixels off the bottom of four mascots — silently, and on
the outline, which is the one part of the house form a cell cannot lose. `gemini-3.1-flash-lite-image`
left its rows comfortably inside the even grid, so the fault would have looked model-specific and
intermittent.

Fixed in `crop_gallery_cells.py`: the cut now snaps to the midpoint of the gutters between the drawn
rows and columns, and falls back to the even grid with a printed warning when the band count does not
match the grid. This is not the paper-trimming that `crop_gallery_cells.py` still refuses to do —
a gutter is empty paper *between* mascots, measured far from any outline, rather than a threshold
pulled tight against one.

## Limitations

- **Two of six cases, two of seven contenders, one sample each.** Enough to price a sheet and shake
  out the instruments. Not enough to rank models, and not evidence about the four cases not run —
  `cast-derived-6`, `cast-original-6`, `variants-single-4` and `cast-derived-3` are all unmeasured,
  including the 3:1 aspect ratio, which is the shape most likely to be mishandled.
- **Identity was not judged.** Mechanical comparability is necessary and not sufficient. The naming
  test and the blend verdict stay human and were not performed here.
- **The order probe is now a rank test.** It proves order was preserved; it does not prove any cell
  matched its lock in any other respect.
- **`gpt-image-2`'s sheet failed comparability on baseline spread (15%) and scale spread (13%)** and
  those numbers are unexplained. They may be real, or the thresholds (18% and 15%) may be tuned too
  tight for a 12-cell grid. One sample cannot tell.
