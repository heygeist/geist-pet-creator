# Image Generation Modes

A Pet can be drawn two ways. Read this before configuring or using the External Image Provider.

## Built-in Image Generation (default)

The agent draws with its own image generation capability. This mode needs no configuration, no API key, and no network access beyond whatever the agent already has. Every Pet uses this mode unless a bundle says otherwise.

## External Image Provider

The bundle draws through OpenRouter over HTTP. Turn it on by writing `imagegen.json` into the Pet source bundle:

```json
{
  "provider": "openrouter",
  "model": "openai/gpt-image-2",
  "output_format": "png",
  "background": "transparent"
}
```

The presence of that file switches the mode. A human asking for a different model in a single run overrides `model` for that run only. The mode never switches on its own: when the built-in capability is unavailable, say so and stop, because a silent switch makes the provenance recorded in every candidate packet false.

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
scripts/eval_providers.py --out provider-eval --max-cost-usd 5
```

That runs each contender over four cases, every one of them sending a reference image, because the
skill does: 56 of a Pet's 57 frames are drawn with an approved identity lock attached. Three cases
are identity-hold — an approved Pet's own art goes in and the model redraws that creature in a new
pose — and one is creativity, sending only the house-style sheet plus a physical description of a
source the model must invent a Pet for.

It reports measured cost, measured duration, a mechanical QA verdict and a rendered silhouette test,
then writes a review page for the naming test and blend verdict that stay human. Duration is
reported because a full Pet is 57 frames, so a model that is lovely at 30s a frame costs half an
hour a pass.

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

Two results worth carrying forward. **Price does not track quality here** — the cheapest model won
outright, and the most expensive produced a weaker character at 11.7× the cost. And **time is a
separate axis the cost column hides**: `gemini-3.1-flash-lite-image` is six times faster than the
default for three times the price, which is the real trade if a pass is blocking someone.

The qwen models were measured and then dropped. Alibaba's filter rejected approved reference art
with `"Input data is suspected of being involved in IP infringement"`. A provider that refuses your
own identity lock cannot serve derived Pets at any price.

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

Every generation produces exactly one frame. Contact sheets have to be sliced, and slicing is the only mechanism by which a part of the Pet lands in the next cell — the defect the final audit exists to catch. Generating one frame per call removes that mechanism instead of auditing for it.

Each call carries the identity lock as references:

1. `sources/canonical-base.png`
2. the previous frame of the same sprite action

So frame 3 is drawn while looking at frame 2, and the sprite action stays coherent without a strip.

## One transform, one run

Scale is decided once, from the first frame of the run, and applied unchanged to every later frame. Fitting each frame to its own bounding box instead would let a crouched pose come out larger than a standing one — the scale popping that [qa-rubric.md](qa-rubric.md) rejects.

The transform is recorded in `candidate-context.json` under `cell_transform`. A frame whose body lands outside safe padding under the shared transform is reported in `frames_outside_safe_padding` rather than quietly rescaled, because rescaling that one frame is the defect.

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --state waiting --variant a --variant-intent "subtle polite lean" \
  --max-images 8 --max-cost-usd 1.00
```

Repair one frame by naming it:

```bash
python "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --state waving --variant repair1 --frames 2
```

## Transparency: request, verify, fall back

Providers vary in whether they honour `background: transparent`, and a provider that ignores it returns an opaque image with no error. So the script checks the result instead of trusting the request:

1. Ask for `background: transparent` with `output_format: png`.
2. Verify the returned image: a real share of the canvas is transparent, and the border is clear.
3. When that fails, ask again for a flat green chroma-key background and key it out locally.

`candidate-context.json` records which path produced each frame under `provenance[].alpha_path`, so a Pet built through the fallback is visible as such later.

## Spend guards

Three variants across nine states at one call per frame is 171 calls. Nothing else in the pipeline notices that, so every run carries a ceiling:

- `--max-images` caps the number of provider calls.
- `--max-cost-usd` caps spend, summed from `usage.cost` on each response.

A run that reaches either ceiling stops and reports what it spent. The chroma-key fallback costs a second call, and it counts against both ceilings.

**These are runaway-loop guardrails, not spend controls.** They are values the caller passes to
itself, so they bound an accident — a loop that requests far more frames than anyone intended — and
nothing else. Read as a security control they would be misleading.

The actual spend control is the **credit limit on the OpenRouter key itself**, set when the key is
minted. It is enforced server-side before a request reaches a provider, so a blocked call costs
nothing upstream, and it holds regardless of what flags a caller passes. Set one. A concurrent burst
can overshoot it slightly.

## What this mode does not change

The External Image Provider changes what draws the pixels. Everything else holds:

- The same approval gates, in the same order.
- The same candidate packets, pre-screened before a human sees them.
- The same subagent authority: subagents write candidate packets, and promotion, approval, export, and install stay with the main agent and the human.
