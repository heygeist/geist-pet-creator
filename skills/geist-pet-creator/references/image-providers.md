# Image Generation Modes

A Pet can be drawn two ways. Read this before configuring or using the External Image Provider.

## Choosing the mode

Choose from **what the running agent can actually do**, once, at bundle setup. Record the choice in the bundle and never re-decide it.

The choice is not a preference. An agent with no image capability cannot use the built-in mode, and pretending otherwise fails at the first draw call. An agent that has one does not need a key or a network round trip.

## Built-in Image Generation

The agent draws with its own image generation capability — Codex with `$imagegen`, or any agent that has one. This mode needs no configuration, no API key, and no network access beyond whatever the agent already has.

## External Image Provider

The bundle draws through OpenRouter over HTTP. Use it whenever the running agent has no image capability of its own. It covers **every** drawing phase, not just animation frames:

| `--action` | Draws | Calls |
| --- | --- | ---: |
| `concept-sheet` | one brainstorm sheet, many concepts on a grid | 1 |
| `canonical-base` | the identity lock, at sprite scale | `--variants` |
| the nine animation states | source frames | one per frame |

Turn it on by writing `imagegen.json` into the Pet source bundle:

```json
{
  "provider": "openrouter",
  "model": "openai/gpt-image-2",
  "output_format": "png"
}
```

No `background` key: how a frame gets its alpha is a fact about the model, so `ALPHA_PATHS` in `generate_candidates.py` decides it. The template used to ship `"background": "transparent"`, which answered HTTP 400 on the default model and then paid for an opaque draw nobody could use — see § Transparency below.

The presence of that file switches the mode. A human asking for a different model in a single run overrides `model` for that run only.

**The mode never switches on its own, and never switches mid-bundle.** Once a bundle has drawn its first candidate, the recorded mode is fixed. Switching would make the provenance recorded in every earlier candidate packet false, and provenance is what someone reads months later to work out why the art went wrong. If the recorded mode becomes unavailable, say so and stop.

### The catalog listing is not proof

**`GET /api/v1/models` omits usable models.** Verified 2026-08-12, authenticated and
unauthenticated, against an account that had just spent real credit:

| Model | In the listing | Answers requests |
| --- | --- | --- |
| `openai/gpt-image-2` (this skill's default) | **no** | **yes**, ~$0.007 a call |
| `x-ai/grok-imagine-image-2.0` | **no** | **yes** |
| `qwen/qwen-image-3-pro` | **no** | **yes** |

This matters because the wrong check is the obvious one. Sessions have looked a pinned model up in
that listing, found it absent, concluded it was fabricated, and repinned working bundles onto
`openai/gpt-5.4-image-2` — which rejects the `output_format` and `background` values this pipeline
sends. The verification feels rigorous, returns a confident negative, and makes things worse.

Model *pages* also resolve for ids the API omits, so `openrouter.ai/openai/gpt-image-2` loading is
not proof either way.

The only authoritative test is a live request:

```
scripts/with_openrouter_key.sh python3 scripts/generate_candidates.py --verify-model <MODEL_ID>
```

It costs about $0.01 and reports reachable, rejected, or unreachable. Allow generous timeouts —
`qwen/qwen-image-3-pro` takes 85 seconds, and a 60-second timeout once produced a false negative.

A pin outside `KNOWN_MODELS` is refused when the bundle config loads, before any spend, with this
same explanation. That failure is deliberate: it is cheaper to stop on a local read than to discover
a bad pin at the provider mid-run.

### Models

Measure, do not trust this list. An earlier version of this table named two models that do not
exist in OpenRouter's catalog and quoted prices for them, and a per-frame cost estimate built on
one of those prices was fiction. Availability and pricing drift; the fix is an instrument, not a
fresher table.

```
scripts/eval_providers.py --out provider-eval --max-cost-usd 6
```

Sheet cases only, when the question is about brainstorming rather than frames:

```
scripts/eval_providers.py --out concept-sheet-eval --max-cost-usd 6 \
  --cases cast-derived-6 cast-original-6 variants-single-4 order-count-6 cast-derived-3 cast-derived-12
```

Every case sends a reference image, because the skill does: 56 of a Pet's 57 frames are drawn with
an approved identity lock attached. Ten cases in three kinds:

- **Identity hold** (3) — an approved Pet's own art goes in and the model redraws that creature in a
  new pose.
- **Creativity** (1) — only the house-style sheet plus a physical description of a source the model
  must invent a Pet for.
- **Concept sheet** (6) — one call returning many mascots on a grid.

A single mascot is scored on whether its identity survived. A sheet is scored on whether its cells
are **comparable**, because comparability is the only reason to draw them in one call rather than
separately, and it is the one property that cannot be recovered afterwards. The sheet metrics are
cell count, containment inside the cell rect, scale spread, baseline spread, and row-major order.

Order gets its own case because it is the one fault nothing downstream can catch. The human clicks
`cell-04` meaning the fourth identity lock they wrote; if the model put that concept elsewhere, they
have chosen a Pet they did not want and nothing says so. `order-count-6` separates its cells by one
machine-readable statistic — the dominant saturated hue of each body panel, stepping around the hue
wheel in cell order — so a misplacement is arithmetic rather than a judgement call. Cyan is
deliberately absent from that palette: the house Sky outline sits at about 197°, and a cyan body
panel would be indistinguishable from the outline every Pet already has.

The eval reports measured cost, measured duration, a mechanical QA verdict and a rendered silhouette
test, then writes a review page for the naming test and blend verdict that stay human. Duration is
reported because a full Pet is 57 frames, so a model that is lovely at 30s a frame costs half an
hour a pass. Sheet costs are kept out of the 57-frame projection: a sheet is not a frame and does
not cost like one.

The full record, including per-case numbers, the human grading, the raw JSON and the method's
known limitations, is in [measurements/2026-08-12-provider-eval.md](../measurements/2026-08-12-provider-eval.md).

Measured 2026-08-12 across four cases — three identity-hold against approved Pet art, one
creativity with no character reference. Cost is a projection from measured per-frame cost across
57 frames; time likewise.

| Model | 57-frame cost | 57-frame time | Alpha | Verdict |
| --- | ---: | ---: | --- | --- |
| **`openai/gpt-image-2`** (default) | **$1.33** | 68 min | params-dropped + chroma | best on cost *and* character completeness |
| `openai/gpt-5-image-mini` | $2.89 | 51 min | **native** | cheapest true-alpha path |
| `google/gemini-3.1-flash-lite-image` | $3.88 | **11 min** | chroma-key | by far the fastest; quality drops |
| `google/gemini-3.1-flash-image` | $7.74 | 22 min | chroma-key | |
| `x-ai/grok-imagine-image-2.0` | $7.98 | 20 min | chroma-key | second on completeness and aesthetic; costly |
| `openai/gpt-5-image` | $9.67 | 35 min | **native** | |
| `google/gemini-3-pro-image` | $15.58 | 42 min | chroma-key | third on completeness; costly |

**Every figure in the cost column budgets the waste.** It is `57 x` a median that billed **two**
calls per frame, because that is what the pipeline did when the eval ran: one discarded opaque draw
and one chroma draw that was kept. `ALPHA_PATHS` now bills one call for every model with a known
alpha path, so halve the column to project 57 drawn frames today — the default lands near **$0.67**.
A real pass is cheaper still, because `running-left` is mirrored rather than drawn: **~$0.57**. Re-run
`eval_providers.py` to replace both projections with a measurement.

Two results worth carrying forward. **Price does not track quality here** — the cheapest model won
outright, and the most expensive produced a weaker character at 11.7× the cost. And **time is a
separate axis the cost column hides**: `gemini-3.1-flash-lite-image` is six times faster than the
default for three times the price, which is the real trade if a pass is blocking someone.

The qwen models were measured and then dropped. Alibaba's filter rejected approved reference art
with `"Input data is suspected of being involved in IP infringement"`. A provider that refuses your
own identity lock cannot serve derived Pets at any price.

### Sheets rank differently from frames

Measured 2026-08-12 over 42 sheets, six cases per model. Full record in
[measurements/2026-08-12-concept-sheet-eval.md](../measurements/2026-08-12-concept-sheet-eval.md).
`comparable` counts sheets whose cells came out usable together — right count, contained, matched
scale and baseline, row-major order intact.

**A sheet has two scores, and they disagree.** `comparable` is mechanical and measures *layout* only.
The human ranking measures *style and identity*, which is the thing a concept sheet exists to let
someone choose between.

| Model | Layout | Human rank | Sheet cost | Median time |
| --- | ---: | ---: | ---: | ---: |
| `google/gemini-3.1-flash-image` | **6/6** | 3rd | $0.0687 | 25.2s |
| `google/gemini-3.1-flash-lite-image` | 5/6 | — | **$0.0343** | **5.5s** |
| `google/gemini-3-pro-image` | 5/6 | — | $0.1386 | 36.2s |
| `openai/gpt-5-image-mini` | 4/6 | — | $0.0520 | 51.8s |
| `x-ai/grok-imagine-image-2.0` | 3/6 | **2nd** | $0.0750 | 14.2s |
| `openai/gpt-5-image` | 2/6 | — | $0.2578 | 51.6s |
| **`openai/gpt-image-2`** (default) | 2/6 | **1st** | **$0.0252** | 33.9s |

**Keep `openai/gpt-image-2` for sheets as well as frames.** It is ranked first by a human for style
and identity, and it is also the cheapest sheet drawer measured. Do not repin it off the mechanical
column: the two failure kinds are not equally serious.

- **Layout faults are recoverable.** A crossing cell is caught at pre-screen and struck out on its
  own, the cropper snaps to the drawn gutters rather than an even grid, and a whole redraw costs
  $0.10.
- **Style faults are not.** A tidy grid of characterless mascots has failed the only job a concept
  sheet has, and nothing downstream fixes it.

Read the mechanical column as *how much pre-screening to expect*, not as quality. `gpt-image-2` at
2/6 will more often need a cell rejected — which is cheap, and which the per-cell policy already
handles.

**The exception is a sheet that must be layout-perfect** — twelve cells, or a sheet going to someone
without a pre-screen pass. `google/gemini-3.1-flash-image` is the only model that passed every case
including the 12-cell stress. Name it for that one run, and expect weaker style in exchange:

```
scripts/with_openrouter_key.sh python3 scripts/generate_candidates.py PetName.pet \
  --action concept-sheet --cells 12 --model google/gemini-3.1-flash-image
```

### The API

`POST {base}/images`, where `{base}` defaults to `https://openrouter.ai/api/v1` and is overridable
with `OPENROUTER_BASE_URL` or `--base-url`. Point it at a local mock to exercise this path without
spending, or at a broker that holds the credential so this process never receives one.

Request fields the skill uses: `model`, `prompt`, `n`, `output_format`, `background`, and `input_references`. A transparent background needs `output_format` of `png` or `webp`. Reference images go in `input_references` as HTTP(S) URLs or base64 data URLs.

The response carries the image at `data[0].b64_json` and the spend at `usage.cost`.

### The key stays in the environment

The key comes from `OPENROUTER_API_KEY` and lives nowhere else. `generate_candidates.py` refuses to run when `imagegen.json` holds a field named like a credential or a value shaped like one, so a bundle can be committed and shared without carrying a key out with it. A bundle cannot redirect the endpoint either — the base URL resolves only from the environment or the command line, so a shared bundle cannot point your credential at someone else's server.

### Supplying the key without handing it over (macOS)

Exporting `OPENROUTER_API_KEY` in a shell profile works everywhere and is the documented fallback
on every platform. It has one real cost: the key is then in the environment of *every* command that
shell runs, so any subprocess, crash dump, or environment listing can see it.

On macOS, `scripts/with_openrouter_key.sh` narrows that. It reads the key from the login keychain
at exec time and exports it into one child process only:

```
security add-generic-password -a "$(id -un)" -s openrouter-geist -w
scripts/with_openrouter_key.sh --check
scripts/with_openrouter_key.sh python3 scripts/eval_providers.py --out provider-eval
```

Omit the value after `-w` — the terminal prompts for it, so the key never enters shell history.
Override the item with `OPENROUTER_KEYCHAIN_SERVICE` and `OPENROUTER_KEYCHAIN_ACCOUNT`.

Two constraints in that script are load-bearing rather than stylistic, and both have comments
saying so:

- It shells out to `/usr/bin/security`. A keychain item created by `security` carries that binary
  on its ACL, which is why the read returns silently from a non-interactive shell. A language
  binding that links Security.framework directly runs as a different binary, misses the ACL, and
  prompts.
- It exports and then execs, rather than `exec env KEY=value`. Passing the value as an argument
  puts it in `argv`, which is readable through `ps` for the life of the process.

**Be clear about what this buys.** It means the key never has to be handed to an agent or a
collaborator, so a cooperative one cannot leak a value it never received. It is not a sandbox: the
key is in the child's environment for the length of the run, and anything running as your user could
read it there. Containment here is by construction, not by enforcement.

### Missing credential: stop, never fall back

If the keychain item is absent the wrapper exits with a diagnostic naming the item and the exact
command to create it. It does **not** fall through to an `OPENROUTER_API_KEY` that happens to be
exported. Dropping silently from the hardened path onto the plain one is the failure the wrapper
exists to prevent, so it is an error rather than a fallback.

The plain environment variable stays fully supported — it is the documented path on every platform
without a login keychain. What is not acceptable is *not knowing which one you are on*. So the
wrapper marks its runs, and every candidate packet records `credential_source` in its provenance:

| Value | Meaning |
| --- | --- |
| `keychain` | the wrapper supplied the key |
| `environment` | a bare `OPENROUTER_API_KEY` supplied it |
| `none` | no credential; the run stopped |

The marker carries no service name and no account. A candidate packet travels between machines, and
where a given machine keeps its key is nobody else's business.

### Where the credential is allowed to travel

Because the endpoint is overridable, the key is only ever sent to OpenRouter itself or to a loopback
address. Any other host gets the request without an `Authorization` header, plus a warning: if that
endpoint needs auth, it should hold its own credential. This stops the quiet accident where a key
left over from an earlier setup rides along to a third party after someone redirects the base URL.

## One frame, one call

Every generation that produces a **frame** produces exactly one. Contact sheets have to be sliced, and slicing is the only mechanism by which a part of the Pet lands in the next cell — the defect the final audit exists to catch. Generating one frame per call removes that mechanism instead of auditing for it.

Each frame call carries the identity lock as references:

1. `sources/canonical-base.png`
2. the previous frame of the same sprite action

So frame 3 is drawn while looking at frame 2, and the sprite action stays coherent without a strip.

### Why a concept sheet is allowed to be a grid

A concept sheet is one call that returns many mascots on a grid, and it does get sliced. That is not a contradiction of the rule above, because the rule is about frames.

**A sheet cell never becomes a frame.** It becomes Image 1 of a `canonical-base` call — a reference the next generation looks at, not pixels that land in `frames/` or in the atlas. A crop that clips a prop shows up as a poor reference, and the canonical-base gate is in front of it. The same slip in a frame strip would reach the spritesheet, which is why frames do not work this way.

The containment risk is real but bounded, so it is measured rather than forbidden: pre-screen checks that no mascot crosses its grid rect, and `crop_gallery_cells.py` cuts to the recorded grid without trimming, so a bad crop is visible rather than silently tidied.

Sheets earn the grid because the grid *is* the product: cells drawn in one call share scale, weight, and lighting, and cells drawn in separate calls do not. A brainstorm exists to be compared.

## One transform, one run

Scale is decided once, from the first frame of the run, and applied unchanged to every later frame. Fitting each frame to its own bounding box instead would let a crouched pose come out larger than a standing one — the scale popping that [qa-rubric.md](qa-rubric.md) rejects.

The transform is recorded in `candidate-context.json` under `cell_transform`. A frame whose body lands outside safe padding under the shared transform is reported in `frames_outside_safe_padding` rather than quietly rescaled, because rescaling that one frame is the defect.

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action waiting --variant a --variant-intent "subtle polite lean" \
  --max-images 8 --max-cost-usd 1.00
```

Repair one frame by naming it:

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action waving --variant repair1 --frames 2
```

`--state` still works as a deprecated alias for `--action`, so existing commands and scripts keep running.

## The two pre-frame actions

Both run before `sources/canonical-base.png` exists, so neither attaches it, and the canonical-base precondition does not apply to them.

Draw a brainstorm sheet — one call, whatever the cell count:

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/ThingConcepts.pet \
  --action concept-sheet --cells 6 --grid 3x2
```

It attaches the house-style reference as Image 2, and the identity reference as Image 1 only for a derived sheet. An original cast sends no Image 1: there is no source to hold.

Render the identity lock at sprite scale:

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action canonical-base --variants 1 \
  --cell-image sources/candidates/concept-sheet-01/cells/cell-04.png
```

`--variants` defaults to 1 when `--cell-image` names an approved sheet cell, because the sheet already showed the human their options. It defaults to 3 without one, which is the normal per-action minimum for a gate nothing has previewed.

## Transparency: the model's capability decides the request

Providers vary in whether they honour `background: transparent`, and only two of the nine measured models return real alpha. `ALPHA_PATHS` in `generate_candidates.py` records which is which, so a frame is asked for the way it can actually be delivered:

| Entry | What the first call asks for | Paid calls per frame |
| --- | --- | ---: |
| `native` | `background: transparent`, verified on the way back | 1 |
| `chroma` | a flat field in this Pet's keying colour, keyed out locally | 1 |
| `chroma-bare` | the same, with `output_format`/`background` omitted because the model rejects them | 1 |
| absent from the table | transparent first, then chroma when the result comes back opaque | 1-2 |

**This is where the largest single cost leak was.** The script used to ask every model for transparency and check the answer, which is right when the capability is unknown and pure waste when it is known. `openai/gpt-image-2` is the default and can never return alpha: the first request 400'd, the second drew an opaque image that was discarded every time, and the third drew the frame. Measured 2026-08-12 on the Karate Crown Guardian build — 2 frames cost 4 calls / $0.101 before the table, and 2 calls / $0.059 after.

Gate on the model id rather than a config flag. The fact belongs to the model, and a flag lets a bundle quietly ask for something the provider cannot do and pay a full draw to find out.

A model absent from the table keeps the ask-verify-fall-back path, which is what an unknown capability deserves. Measure it with `eval_providers.py`, then add the entry.

### The keying colour is chosen per Pet, not fixed

`CHROMA_KEY` was pure green, hardcoded, and nothing consulted the Pet before using it. FuseSprout's body is `#9FC351`. Five of six `review` frames keyed; the sixth came back opaque, took the state with it, and cost $0.14. **When this fires it is a total loss** — the background is baked into the art, so the frame is not recoverable at any price.

`choose_chroma_key` now reads `sources/canonical-base.png` once per bundle and picks the backdrop furthest from the colours the Pet actually uses, scoring by the **nearest** visible pixel rather than the average: a backdrop the Pet touches only on its outline is exactly the dangerous one, because the outline is what shows when it goes.

Distance is not the only test, and this is the part worth knowing. The keyer also removes a desaturated **fringe**, and that test deletes colours the distance test would have spared. Cyan sits 137 from the house form's sky-blue outline — comfortably past the tolerance of 72 — and erases it on every frame, because a sky blue is exactly "green and blue both strong, red weak". So a candidate that would catch any of the Pet's colours in its fringe test scores zero and cannot win, however far away it measures. Measured on a house-form Pet: cyan scores 0, blue 239, green 271, magenta 334.

The practical result is the rule the report asked for — magenta for a green Pet, green for a magenta one — reached by measurement rather than by a table that encodes one assumption. The chosen colour is named in the frame prompt, used by the local key-out, and recorded in provenance beside `alpha_path`. A run whose best available backdrop is still close to the Pet warns on stderr before spending.

`candidate-context.json` records which path produced each frame under `provenance[].alpha_path`, alongside `alpha_path_source` — `table` or `probed` — and `chroma_key`, so a frame that keyed badly is diagnosed from the pair.

None of this applies to `--action concept-sheet`. A sheet asks for opaque warm off-white paper on purpose — the negative space between cells is what keeps the mascots readable — so there is nothing to verify and nothing to fall back to. Cells become reference images, and a reference image does not need alpha.

## Spend guards

A ceiling is a runaway-loop guardrail, not a spend control. Every run carries one:

- `--max-images` caps the number of provider calls.
- `--max-cost-usd` caps spend, summed from `usage.cost` on each response.

The defaults are sized per action, because an 8-frame state and a one-call sheet are not the same accident:

| `--action` | `--max-images` | `--max-cost-usd` | Transparency fallback |
| --- | ---: | ---: | --- |
| `concept-sheet` | 1 | $0.10 | none — the sheet is drawn on opaque warm off-white paper by design |
| `canonical-base` | `--variants` x2 | $0.25 | possible, so the image cap leaves room for one retry per variant |
| the nine animation states | 24 | $3.00 | possible |

A one-call sheet under a $3.00 ceiling has no real guard, so a mistyped flag would keep drawing until something else noticed. Under $0.10 it stops immediately.

### Pre-flight stops a bad state at two frames

A ceiling only catches a runaway. What actually cost money was a state that ran to completion carrying a defect that was already in frame 0.

So the mechanical checks get a veto. After each of the first `PREFLIGHT_FRAMES` (2) frames, the run stops if the cell fails any of:

- **edge contact** — the body reaches outside safe padding
- **opaque fraction** — the background did not key out, so a panel or backdrop came back as art
- **area delta** — the body's bbox is more than 35% off frame 0's, so it is not the same character moving

The run still writes its packet, so the frames drawn are evidence rather than a loss, and `ok` comes back `false` with the failing check named. That is a prompt or a canonical-base problem: drawing the state again unchanged spends the same money for the same result.

What pre-flight cannot see is anatomy. A state that draws legs fits, keys out, and holds its area perfectly. Legs are the prompt's job — `LEGLESS_MOTION` in `geist_house.py`.

A run that reaches either ceiling stops and reports what it spent. The chroma-key fallback costs a second call and counts against both ceilings, so any action that can fall back is capped with room for it. A concept sheet never falls back: it asks for paper, and paper is what it wants.

**These are runaway-loop guardrails, not spend controls.** They are values the caller passes to
itself, so they bound an accident — a loop that requests far more frames than anyone intended — and
nothing else. Read as a security control they would be misleading.

The actual spend control is the **credit limit on the OpenRouter key itself**, set when the key is
minted. It is enforced server-side before a request reaches a provider, so a blocked call costs
nothing upstream, and it holds regardless of what flags a caller passes. Set one. A concurrent burst
can overshoot it slightly.

## The spend ledger

A ceiling bounds an accident. The ledger answers a different question — what did this actually cost —
and it is the only answer available for a build nobody watched.

Every provider call appends one line, in two places:

| File | Job | If the write fails |
| --- | --- | --- |
| `<bundle>/qa/spend.jsonl` | what this Pet cost | **fatal** — a Pet that cannot account for its own art is a defect |
| `${GEIST_HOME:-$HOME}/.geist/spend.jsonl` | what every Pet on this machine cost | **warning** — it is rebuildable from bundle ledgers |

The split follows what is recoverable, not what is important. Home resolution matches how
`export_geist_pet.py` resolves an install target, so one `GEIST_HOME` moves the Pets and their
receipts together.

**Lines are appended when the provider answers, not when the packet lands.** Cost already appears in
every candidate packet under `provenance[].usage_cost_usd`, so a ledger that only summed packets
would look redundant — and would be blind to exactly the spend worth finding. A run stopped at
`--max-images` writes no packet at all. A `--verify-model` probe writes no packet. Both spent money.

One line, keyed on `pet.json`'s `id` because a bundle path changes when someone renames a directory
and an id does not:

```json
{"schema":1,"at":"2026-08-12T10:47:59Z","pet_id":"rainy-geist","bundle":"/abs/path/Rainy.pet",
 "kind":"draw","action":"waiting","candidate_id":"waiting-a","frame":0,"mode":"auto",
 "provider":"openrouter","model":"openai/gpt-image-2","images":1,"cost_usd":0.0231,"priced":true}
```

`mode` carries the decision mode from `--mode`, so a Pet whose frames nobody chose stays visible as
one months later. `priced` is false with `cost_usd: null` when no price was reported — Built-in Image
Generation reports none. Those images are **counted, never estimated**: a plausible number in a file
that reads like a receipt is worse than an honest gap.

Concurrent writers are safe by construction. Each line is one `write()` on an `O_APPEND` handle, held
under 4096 bytes; a line that would run over sheds its optional fields rather than its atomicity.
That matters because this skill runs candidate subagents in parallel, and eight of them appending at
once is the normal case rather than the exceptional one.

Read it with `spend_report.py`, which needs no credential:

```bash
python "$SKILL_DIR/scripts/spend_report.py" /absolute/path/PetName.pet --by-action
python "$SKILL_DIR/scripts/spend_report.py" /absolute/path/work-directory
python "$SKILL_DIR/scripts/spend_report.py" --home
```

Asking for `--home` and a bundle in the same run is refused: both files hold the same lines, so
summing them would double every number in the report.

Under Built-in Image Generation nothing makes an HTTP call, so the agent records its own draws:

```bash
python "$SKILL_DIR/scripts/spend_report.py" --record --pet /absolute/path/PetName.pet \
  --action waiting --images 6 --unpriced --mode auto
```

`--record` refuses to run without either `--cost-usd` or `--unpriced`. A missing price is not zero.

## What this mode does not change

The External Image Provider changes what draws the pixels. Everything else holds:

- The same gates, in the same order. **Which of them a human answers is the decision mode's business, not this mode's** — see SKILL.md § Decision Modes. `--mode` only records the answer; it never moves a gate.
- The same candidate packets, pre-screened before anything is promoted.
- The same subagent authority: subagents write candidate packets, and promotion, approval, export, and install stay with the main agent and the human.
