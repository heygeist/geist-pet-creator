# Concept-sheet eval — 2026-08-12

Seven contenders over six concept-sheet cases. Raw data:
[`2026-08-12-concept-sheet-eval.json`](2026-08-12-concept-sheet-eval.json). The smoke test that
preceded it, and the two instrument defects it found, are in
[`2026-08-12-concept-sheet-smoke.md`](2026-08-12-concept-sheet-smoke.md).

**34 provider calls, $3.1052.** Forty-two were planned; eight never ran, for two different reasons
recorded below. A sheet needs no fallback, so calls and sheets are the same number.

```bash
scripts/with_openrouter_key.sh python3 scripts/eval_providers.py \
  --out concept-sheet-eval --max-images 60 --max-cost-usd 6.00 \
  --cases cast-derived-6 cast-original-6 variants-single-4 order-count-6 cast-derived-3 cast-derived-12
```

## Results

`comparable` counts sheets whose cells came out usable together: right count, each contained in its
cell, matched scale and baseline, row-major order intact.

| Model | Comparable | Sheet cost | Median time |
| --- | ---: | ---: | ---: |
| **`google/gemini-3.1-flash-image`** | **5/6** | $0.0687 | 25.2s |
| `google/gemini-3.1-flash-lite-image` | 4/6 | **$0.0343** | **5.5s** |
| `x-ai/grok-imagine-image-2.0` | 4/6 | $0.0750 | 13.6s |
| `google/gemini-3-pro-image` | 3/6 | $0.1386 | 36.1s |
| `openai/gpt-5-image-mini` | 2/6 | $0.0520 | 51.8s |
| `openai/gpt-5-image` | 2/6 | $0.2578 | 51.6s |
| `openai/gpt-image-2` (skill default) | **1/6** | $0.0252 | 33.9s |

## What it decided

**The default model is the worst sheet drawer measured, and should not be repinned.**
`openai/gpt-image-2` won the frame eval on cost and character completeness, and it comes last here at
1 of 6. These are different jobs. A frame redraws one approved creature; a sheet places many
creatures on a grid at matched scale and baseline, and that is a layout skill the frame eval never
tested. **Leave `DEFAULT_MODEL` alone** — it is still the right default for the 56 frames that make up
almost all of a Pet's cost. Consider naming a different model for the one sheet call instead, which
the per-run `--model` override already allows without touching the bundle.

**If a sheet model is named, `google/gemini-3.1-flash-image` is the one.** Best comparability at 5 of
6, mid-price, mid-speed. `gemini-3.1-flash-lite-image` is the value option: 4 of 6, cheapest of the
credible models, and **six times faster than the winner** — 5.5s against 25.2s.

**Price still does not track quality.** `openai/gpt-5-image` is the most expensive sheet drawer at
$0.2578 — ten times `gpt-image-2` — and manages 2 of 6. The cheapest credible model beats it twice
over.

## Two failures that were not model failures

**`cast-derived-3` failed on all seven contenders, and the fault was in this repo.** Every attempt
returned HTTP 400 with a `ZodError`. `aspect_ratio` is a **closed enum**, and the grid table asked for
`3:1`, which is not in it. The provider rejects the request before any model sees it.

The accepted list, from the error body:

```
1:1  1:2  1:4  1:8  2:1  2:3  3:2  3:4  4:1  4:3  4:5  5:4  8:1  9:16  16:9  9:19.5  19.5:9
```

Two of the eight shipped grid layouts were illegal: `3x1` at `3:1` and `5x2` at `5:2`. Both now take
`2:1`, the nearest legal ratio, which makes their cells portrait rather than square — acceptable,
since a Pet is taller than it is wide. `geist_house.py` now holds `PROVIDER_ASPECT_RATIOS` and
refuses an illegal value locally, on a free read, rather than at the provider mid-run.

Worth naming the shape of this mistake: seven identical 400s across seven unrelated models read like
a provider outage. It is not the pattern that makes anyone check their own constant.

**`x-ai/grok-imagine-image-2.0` lost its last case to the key's credit limit.**

```
HTTP 403 {"error":{"message":"Key limit exceeded (total limit)","code":403}}
```

That is the server-side ceiling on the OpenRouter key working exactly as the provider-eval record
says it should — enforced upstream, outside this process's reach, regardless of what `--max-cost-usd`
allowed. The eval's own ceilings never fired: it stopped at $3.11 of a permitted $6.00. **Raise the
key's credit limit before the next run.**

## Estimate against outcome

Predicted $1.50–$5.20, most likely near $3.00, against a measured **$3.1052**. The range was right,
and it was wide for the right reason: five of seven contenders had no sheet price at the time. Note
the true full-run cost is higher than $3.11 — eight of the forty-two sheets never drew, and the seven
missing `cast-derived-3` sheets alone would have added roughly $0.60.

## Limitations

- **`cast-derived-3` is still unmeasured.** The 3-cell layout has never successfully drawn. Its ratio
  changed from an illegal `3:1` to `2:1`, and that replacement is untested — the cells are now
  portrait at 0.67, which no case has yet exercised.
- **`cast-derived-12` was the hardest case for everyone**: only `gemini-3.1-flash-image` passed it.
  Whether that is a real ceiling on twelve cells or a symptom of thresholds tuned on six is not
  settled by one run per model.
- **Identity was not judged.** Comparability is mechanical and says nothing about whether a cell is
  nameable. The naming test and blend verdict stay human and were not performed.
- **One sample per model per case.** Enough to rank, not enough to characterise variance.
- **`openai/gpt-image-2`'s baseline and scale spread reproduced** across the full run rather than
  being a one-sample artefact of the smoke test. The thresholds may still be tuned tight, but the
  model is genuinely the weakest at grid layout.
