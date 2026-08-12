# Concept-sheet eval — 2026-08-12

Seven contenders over six concept-sheet cases. Raw data:
[`2026-08-12-concept-sheet-eval.json`](2026-08-12-concept-sheet-eval.json). The smoke test that
preceded it, and the two instrument defects it found, are in
[`2026-08-12-concept-sheet-smoke.md`](2026-08-12-concept-sheet-smoke.md).

**42 sheets, $3.7544, across three runs.** The first run drew 34 and lost eight to two faults
recorded below; both were fixed and the missing eight redrawn. The JSON is the merged set. A sheet
needs no fallback, so calls and sheets are the same number.

```bash
scripts/with_openrouter_key.sh python3 scripts/eval_providers.py \
  --out concept-sheet-eval --max-images 60 --max-cost-usd 6.00 \
  --cases cast-derived-6 cast-original-6 variants-single-4 order-count-6 cast-derived-3 cast-derived-12
```

## Results

`comparable` counts sheets whose cells came out usable together: right count, each contained in its
cell, matched scale and baseline, row-major order intact.

**This measures layout only.** It says nothing about whether a cell is nameable or well drawn. The
human verdict below is the other axis, and it disagrees.

| Model | Comparable | Sheet cost | Median time |
| --- | ---: | ---: | ---: |
| **`google/gemini-3.1-flash-image`** | **6/6** | $0.0687 | 25.2s |
| `google/gemini-3.1-flash-lite-image` | 5/6 | **$0.0343** | **5.5s** |
| `google/gemini-3-pro-image` | 5/6 | $0.1386 | 36.2s |
| `openai/gpt-5-image-mini` | 4/6 | $0.0520 | 51.8s |
| `x-ai/grok-imagine-image-2.0` | 3/6 | $0.0750 | 14.2s |
| `openai/gpt-5-image` | 2/6 | $0.2578 | 51.6s |
| `openai/gpt-image-2` (skill default) | 2/6 | $0.0252 | 33.9s |

Every Gemini model places mascots on the implied grid more consistently than any OpenAI model. Twelve
cells is the ceiling: only `gemini-3.1-flash-image` passed it, so the 12-cell cap stands but only one
measured model reaches it.

### The first version of this table was wrong

Containment was scored against an **even grid**. `crop_gallery_cells.py` does not cut on an even
grid — it snaps to the drawn gutters, because models put their rows where they like.

So the metric reported disagreement with an assumption as though it were damage. Checked directly:
17 of `openai/gpt-image-2`'s cells were called "crossing" across five sheets, and **all 17 crop clean
once snapped**. Not one was clipped. Correcting it moved five verdicts — `gpt-5-image-mini` 2→4,
`gemini-3-pro` 4→5, `grok` 4→3 — and flattened the table from `6,5,4,4,2,2,1` to `6,5,5,4,3,2,2`.

A fault only counts if it survives the thing that repairs it. `mechanical_pass_even_grid` in the JSON
preserves the original verdicts.

## Human grading

The ranking below is the human's, from the review page. It is the naming and blend judgement the
mechanical score deliberately does not attempt.

1. **`openai/gpt-image-2`** — best style and identity.
2. `x-ai/grok-imagine-image-2.0` — nearly as good, but expensive.
3. `google/gemini-3.1-flash-image` — style drops; identity held acceptably.

**The two axes disagree, and that is the most useful result in this eval.** The model a human ranks
first for style comes second-to-last on layout. The model that tops the layout table is third on
looks.

They do not contradict each other, because they measure different things — and only one of them is
recoverable:

- **Layout faults are cheap.** A crossing cell is caught at pre-screen and rejected on its own; the
  cropper snaps to gutters; a sheet redraw costs $0.10. The per-cell failure policy exists precisely
  so one weak cell does not cost the sheet.
- **Style faults are not.** A concept sheet exists so a human can choose a concept by looking at it.
  A well-aligned grid of characterless mascots has failed at the only job it had, and no downstream
  step recovers it.

So the human axis decides which model draws concepts, and the mechanical axis decides how much
pre-screening to expect from it.

## What it decided

**`openai/gpt-image-2` stays the default, for sheets as well as frames.** It won the frame eval on
cost and character completeness, and the human ranked it first for sheet style and identity too. It
is also the cheapest sheet drawer measured, at $0.0252. Nothing here justifies a change.

An earlier draft of this record recommended naming a Gemini model for the sheet call. **That
recommendation was wrong and is withdrawn.** It rested on the mechanical table alone, at a point when
that table was also over-strict, and it would have traded the thing a concept sheet is for — a human
looking at concepts and picking one — for grid tidiness that the cropper already handles.

**What the mechanical axis is actually good for: knowing what to expect at pre-screen.**
`gpt-image-2` sits at 2 of 6, so its sheets are the likeliest to need a cell rejected. Budget for
that, and note it is cheap: one cell struck out costs nothing, and a full redraw costs $0.10.

**If a sheet ever needs to be layout-perfect** — twelve cells, or a sheet going straight to someone
without pre-screening — `google/gemini-3.1-flash-image` is the only model that passed every case,
including the 12-cell stress. Treat that as the exception, not the default, and expect weaker style
in exchange.

**Price still does not track quality on either axis.** `openai/gpt-5-image` costs ten times
`gpt-image-2` per sheet, scores 2 of 6 mechanically, and did not place in the human ranking.

**Price still does not track quality.** `openai/gpt-5-image` is the most expensive sheet drawer at
$0.2578 — ten times `gpt-image-2` — and manages 2 of 6. The cheapest credible model beats it twice
over.

## Two failures that were not model failures

**`cast-derived-3` failed on all seven contenders, and the fault was in this repo.** Every attempt
returned HTTP 400 with a `ZodError`. `aspect_ratio` is a **closed enum**, and the grid table asked for
`3:1`, which is not in it. The provider rejects the request before any model sees it.

The schema's accepted list, from the error body:

```
1:1  1:2  1:4  1:8  2:1  2:3  3:2  3:4  4:1  4:3  4:5  5:4  8:1  9:16  16:9  9:19.5  19.5:9
```

**That list is not the supported set, and believing it was cost a second round of the same bug.**
The first fix moved `3x1` and `5x2` onto `2:1`, which is in the schema. It fails anyway, with a
different 400:

```
schema reject:   ZodError ... invalid_value                          3:1, 5:2
provider reject: No provider for <model> supports the
                 requested parameters                                2:1, 4:1, and presumably
                                                                     8:1, 1:8, 16:9, 9:16
```

Probed directly, one ratio at a time, on two models — $0.24:

| Ratio | `openai/gpt-image-2` | `google/gemini-3.1-flash-lite-image` |
| --- | --- | --- |
| `1:1` | OK | OK |
| `3:2` | OK | OK |
| `4:3` | OK | OK |
| `2:1` | **no provider** | **no provider** |
| `4:1` | **no provider** | not probed |

**Only near-square ratios are served.** So `PROVIDER_ASPECT_RATIOS` is now the *measured* set —
`1:1`, `3:2`, `4:3` — not the schema enum, and the grid is chosen to fit the ratio rather than the
other way round. Counts that do not tile one of the three take the next grid up and leave cells
empty.

That made it **three** broken layouts, not two. `8 → 4x2 @ 2:1` was wrong in the original table as
well, and no eval case used eight cells, so nothing caught it. It is now `3x3` with one empty cell.

Two things worth carrying forward. Seven identical 400s across seven unrelated models read like a
provider outage, not like a typo in a local constant — the symptom points away from the cause. And a
schema enum is a *validator's* list, not a capability list: passing validation only means the request
was well-formed enough to be refused later. Probe the ratio against a real model, the same way a
model id is only settled by a live request.

**`x-ai/grok-imagine-image-2.0` lost its last case to the key's credit limit.**

```
HTTP 403 {"error":{"message":"Key limit exceeded (total limit)","code":403}}
```

That is the server-side ceiling on the OpenRouter key working exactly as the provider-eval record
says it should — enforced upstream, outside this process's reach, regardless of what `--max-cost-usd`
allowed. The eval's own ceilings never fired: it stopped at $3.11 of a permitted $6.00. **Raise the
key's credit limit before the next run.**

## Estimate against outcome

Predicted $1.50–$5.20, most likely near $3.00. Measured **$3.7544** for the complete 42 sheets
($3.1052 for the first 34, $0.6492 for the eight redrawn). The range held and the midpoint was close;
it was wide for the right reason, since five of seven contenders had no sheet price when the estimate
was made.

The earlier $1.50 figure quoted before any sheet had been drawn was wrong by 2.5x, because it was
extrapolated from `openai/gpt-image-2` alone — the cheapest of the seven. Sheet price also does not
track frame price: `gemini-3.1-flash-lite-image` costs three times more than `gpt-image-2` per frame
and about the same per sheet.

## Limitations

- **The empty-rect layout works, but only on Gemini.** All seven models drew exactly 3 mascots on the
  `2x2` grid — **not one filled the spare rect**, which was the risk worth checking, and it does not
  happen. Scale held everywhere (cv 0.048–0.103). Baselines did not: the three Gemini models came in
  at 7–14%, and the three OpenAI models plus grok at 16%, 20%, 44% and 61%. The OpenAI models also
  crossed *every* cell rect, because they compose three mascots freely rather than onto a 2x2 with a
  hole in it. The 5, 8 and 10 layouts share the empty-rect shape and are still untested.
- **Only two of seven models were probed for aspect-ratio support.** `1:1`, `3:2` and `4:3` are
  verified on `openai/gpt-image-2` and `google/gemini-3.1-flash-lite-image` only. The other five drew
  on those ratios throughout, which is consistent, but they were never probed directly.
- **`cast-derived-12` was the hardest case for everyone**: only `gemini-3.1-flash-image` passed it,
  now confirmed across all seven. Whether that is a real ceiling on twelve cells or a symptom of
  thresholds tuned on six is not settled by one run per model.
- **Identity was not judged.** Comparability is mechanical and says nothing about whether a cell is
  nameable. The naming test and blend verdict stay human and were not performed.
- **One sample per model per case.** Enough to rank, not enough to characterise variance.
- **`openai/gpt-image-2`'s baseline and scale spread reproduced** across the full run rather than
  being a one-sample artefact of the smoke test. The thresholds may still be tuned tight, but the
  model is genuinely the weakest at grid layout.
