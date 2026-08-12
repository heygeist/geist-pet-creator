# Provider eval — 2026-08-12

The measurement that chose this skill's default image model. Raw data:
[`2026-08-12-provider-eval.json`](2026-08-12-provider-eval.json).

Re-run rather than trusting these numbers as they age — model availability and pricing both drift,
and this repo has already shipped one cost estimate anchored to a model that could not be reached:

```bash
scripts/with_openrouter_key.sh python3 scripts/eval_providers.py --out provider-eval --max-cost-usd 4.5
```

**60 provider calls, $4.0913, under the $4.50 ceiling.** 9 models x 4 cases = 36 frames; the call
count is higher because 7 of 9 models needed a fallback call.

## Method

Every call carried a reference image, because the skill does: 56 of a Pet's 57 frames are drawn with
an approved identity lock attached. A model that draws well from a bare prompt and drifts when shown
a character is useless here, so an eval that omits references measures the wrong job.

| Case | Kind | Reference sent | Tests |
| --- | --- | --- | --- |
| `doraemon` | identity hold | `DoraemonGeist.pet/frames/idle/00.png` | medium — simple cue shapes |
| `gon-hxh` | identity hold | `HunterXHunterGeistConcepts.pet/sources/canonical-base.png` | hard — one attached prop |
| `vegeta-dbz` | identity hold | `DragonBallConcepts.pet/sources/canonical-base.png` | hardest — spiky hair silhouette |
| `invent-slayer` | creativity | `assets/geist-house-style.jpg` **only** | invent a new Pet from physical description |

The creativity case sends no picture of the character — only the house-style sheet and a physical
description (red-tipped dark hair, forehead scar, green/black check, sun-disc earrings). Never the
source's name, per `references/identity-blend.md`: a name drags the whole franchise art style in.

Scoring is two-stage. The script auto-scores the mechanical rubric and renders the silhouette test;
a human does the naming test and the blend verdict.

## Results

| Model | ret | mech | median | 57-frame $ | 57-frame time | alpha path |
| --- | --- | --- | ---: | ---: | ---: | --- |
| **`openai/gpt-image-2`** | 4/4 | 4/4 | 72.1s | **$1.33** | 68 min | params-dropped+chroma |
| `openai/gpt-5-image-mini` | 4/4 | 4/4 | 54.2s | $2.89 | 51 min | **native** |
| `qwen/qwen-image-3` | 3/4 | 3/4 | 128.7s | $3.76 | 122 min | chroma-key |
| `google/gemini-3.1-flash-lite-image` | 4/4 | 4/4 | **11.4s** | $3.88 | **11 min** | chroma-key |
| `google/gemini-3.1-flash-image` | 4/4 | 4/4 | 23.6s | $7.74 | 22 min | chroma-key |
| `x-ai/grok-imagine-image-2.0` | 4/4 | 4/4 | 21.5s | $7.98 | 20 min | chroma-key |
| `qwen/qwen-image-3-pro` | 3/4 | 3/4 | 294.4s | $8.89 | **4.7 hours** | chroma-key |
| `openai/gpt-5-image` | 4/4 | 4/4 | 36.5s | $9.67 | 35 min | **native** |
| `google/gemini-3-pro-image` | 4/4 | 4/4 | 44.2s | $15.58 | 42 min | chroma-key |

Per case, duration and cost:

| Model | doraemon | gon-hxh | vegeta-dbz | invent-slayer |
|---|---|---|---|---|
| `google/gemini-3.1-flash-lite-image` | 26s / $0.0678 | 8s / $0.0687 | 12s / $0.0683 | 11s / $0.0678 |
| `google/gemini-3.1-flash-image` | 23s / $0.1360 | 24s / $0.1356 | 28s / $0.1356 | 21s / $0.1371 |
| `google/gemini-3-pro-image` | 45s / $0.2726 | 44s / $0.2739 | 125s / $0.2727 | 41s / $0.2752 |
| `openai/gpt-5-image-mini` | 50s / $0.0507 | 42s / $0.0341 | 60s / $0.0507 | 59s / $0.0508 |
| `openai/gpt-5-image` | 37s / $0.1696 | 41s / $0.1697 | 35s / $0.1696 | 36s / $0.1701 |
| `openai/gpt-image-2` | 51s / $0.0175 | 66s / $0.0243 | 78s / $0.0243 | 78s / $0.0224 |
| `qwen/qwen-image-3` | **failed** | 149s / $0.0660 | 125s / $0.0660 | 129s / $0.0660 |
| `qwen/qwen-image-3-pro` | **failed** | 327s / $0.1560 | 238s / $0.1560 | 294s / $0.1560 |
| `x-ai/grok-imagine-image-2.0` | 19s / $0.1400 | 22s / $0.1400 | 21s / $0.1400 | 30s / $0.1400 |

## Human grading

Mechanical QA passed everything that returned, so it did not discriminate. The ranking is the
human's, from the review page:

1. **`openai/gpt-image-2`** — best on both pricing and character completeness.
2. `x-ai/grok-imagine-image-2.0` — second on completeness and aesthetic, faster, but too expensive.
3. `google/gemini-3-pro-image` — third on completeness and aesthetic, too expensive.
4. `google/gemini-3.1-flash-lite-image` — acceptable, but dearer than the winner and both aesthetic
   and completeness drop.

## What it decided

- **Default model: `openai/gpt-image-2`.** Applied to `DEFAULT_MODEL` and `imagegen.example.json`.
- **`--max-cost-usd` default: $3.00**, roughly 2x a measured pass.
- **Key credit limit: $10**, the only server-enforced ceiling.
- **The qwen models were removed from the skill** (see below).

## Findings worth carrying forward

**Price does not track quality.** The cheapest model won outright on character completeness; the most
expensive produced a weaker result at 11.7x the cost. Any default that assumes the pro tier is the
safe choice would be wrong and expensive here.

**Time is a separate axis the cost column hides.** `gemini-3.1-flash-lite-image` runs a pass six
times faster than the default for three times the price. `qwen-image-3-pro` needs 4.7 hours for one
Pet. Neither fact is visible in cost alone.

**Only 2 of 9 models return true alpha unaided.** The chroma-key fallback is the normal path, not an
edge case, and it doubles cost and time for the other seven. `openai/gpt-image-2` chains both
fallbacks — it rejects `output_format`/`background` outright, then returns opaque pixels.

**Both qwen models refuse recognisable reference art.** Only on `doraemon`, the most literal of the
three references:

```
HTTP 400 {"error":{"message":"Input data is suspected of being involved in IP infringement",
"code":400,"metadata":{"provider_name":"Alibaba"}}}
```

A provider that rejects your own approved identity lock cannot serve derived Pets at any price, so
they are out of `KNOWN_MODELS` regardless of their otherwise competitive numbers.

## Limitations

- **`57-frame $` and `57-frame time` are projections** from four frames, not measurements of a pass.
  The independent end-to-end run later recorded $0.018416 for one `gpt-image-2` frame, inside this
  eval's $0.0175–$0.0243 band, which is the only cross-check performed.
- **One frame per model per case.** Enough to compare, not enough to characterise variance.
- **Mechanical pass is necessary, not sufficient.** It says the frame is technically usable, not that
  the character survived.
- **A superseded first run exists.** It sent bare prompts with no references and is not recorded
  here, because it measured a job this skill never does. Its one durable finding — that the Gemini
  models return opaque pixels rather than honouring `background: transparent` — is reflected above in
  their `chroma-key` alpha path.
