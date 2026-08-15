# Image generation modes

Choose the drawing mode once at bundle setup. The mode changes who draws pixels;
it does not change workflow-profile approval gates.

## Built-in image generation

Use the running agent's image capability when available. No bundle credential or
`imagegen.json` is needed. Record each draw as unpriced so the image count remains
visible:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/spend_report.py" --record \
  --pet /absolute/path/PetName.pet --action waiting \
  --images 7 --unpriced --mode auto
```

Unpriced means the client reported no per-image charge; it does not mean free.

## External provider

The external generator calls OpenRouter for concept sheets, canonical bases, and
animation frames. Add `imagegen.json` to the bundle:

```json
{
  "provider": "openrouter",
  "model": "openai/gpt-image-2",
  "output_format": "png"
}
```

The key comes only from `OPENROUTER_API_KEY`. The generator refuses fields named
like credentials and values shaped like secrets. The endpoint comes from
`OPENROUTER_BASE_URL` or `--base-url`, never from a shared bundle.

Before a request, disclose and obtain authority for:

1. provider, endpoint, and model;
2. requested and cumulative image counts;
3. maximum images and US-dollar cost;
4. prompts and local reference images that will be uploaded.

Always pass `--max-images` and `--max-cost-usd`. They stop runaway work but do
not replace user consent or a provider-side credit limit.

## Model pins

The generator accepts only model IDs in `KNOWN_MODELS`. That is a fail-closed
compatibility allowlist, not a promise that availability, price, or quality has
stayed unchanged.

Do not infer that a model is unavailable because it is absent from a catalog
listing. A live request is the authoritative compatibility check, and it is
billable. Disclose the provider, model, one-request estimate/ceiling, and uploaded
test prompt; obtain authority before running:

```bash
"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" \
  --verify-model openai/gpt-image-2
```

Do not change `KNOWN_MODELS`, the default model, or an alpha-path entry from a
catalog page alone. A maintainer change needs a sanitized, cost-capped live
measurement recorded under the repository's `evidence/` directory.

## macOS keychain wrapper

Environment export works on every supported platform. On macOS the wrapper can
limit key exposure to one child process:

```bash
security add-generic-password -a "$(id -un)" -s openrouter-geist -w
"$SKILL_DIR/scripts/with_openrouter_key.sh" --check
```

Omit the value after `-w`; the terminal prompts without putting it in shell
history. Override the item with `OPENROUTER_KEYCHAIN_SERVICE` and
`OPENROUTER_KEYCHAIN_ACCOUNT`.

## Drawing actions

Concept sheet:

```bash
"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/Concepts.pet \
  --action concept-sheet --locks-file /absolute/path/locks.json \
  --cells 6 --grid 3x2 --mode supervised \
  --max-images 1 --max-cost-usd 0.10
```

Canonical base:

```bash
"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action canonical-base --variants 3 --mode supervised \
  --max-images 6 --max-cost-usd 0.25
```

One animation state:

```bash
"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action waiting --variant a --variant-intent "subtle polite lean" \
  --mode auto --max-images 14 --max-cost-usd 0.50
```

Repair one frame by naming it with `--frames`, for example `--frames 2`.
`running-left` mirrors approved `running-right` frames without a provider call
unless `--independent-left` is explicitly requested.

## Transparency and registration

`ALPHA_PATHS` records how an allowed model produces alpha:

- `native`: request transparent output;
- `chroma`: request a flat green field, then key it locally;
- `chroma-bare`: omit incompatible output fields and use the chroma path.

This avoids paying for a known-unusable transparent draw. Candidate provenance
records the selected alpha path. Preflight stops a state when its first frames
fail safe padding, background extraction, or area consistency.

Scale is decided once from the first state frame and applied unchanged to every
later frame. A frame that no longer fits is reported rather than individually
rescaled, because per-frame fitting causes visible scale popping.

## Spend guards and ledger

Per-action defaults exist, but callers still pass explicit ceilings:

| Action | Default image guard | Default cost guard |
| --- | ---: | ---: |
| concept sheet | 1 | $0.10 |
| canonical base | variants × 2 | $0.25 |
| animation state | 24 | $3.00 |

Quick and Full Automation add a workflow-level maximum of 64 generated images
per normal complete pass. Read cumulative images from `qa/spend.jsonl`; stop at
64. Studio calculates a new ceiling from the selected candidate count and waits
for authority.

Every answered provider request appends a line immediately:

| File | Purpose | Write failure |
| --- | --- | --- |
| `<bundle>/qa/spend.jsonl` | authoritative Pet ledger | fatal |
| `${GEIST_HOME:-$HOME}/.geist/spend.jsonl` | machine-wide convenience view | warning |

The bundle ledger captures failed runs and model probes that never produced a
candidate packet. Read it without credentials:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/spend_report.py" \
  /absolute/path/PetName.pet --by-action
```

Do not combine `--home` with bundle paths; the same calls may appear in both and
would be double-counted.

## Failure behavior

- Missing key, unknown model, malformed config, or an unreadable ledger fails
  before useful work continues.
- Each candidate packet records prompts, inputs, provider/model, provenance, and
  partial output so a capped run can resume.
- A preflight failure stops after evidence is written. Fix the character bible,
  canonical base, or prompt rather than repeating the same paid call.
- Never log authorization headers, environment values, or response fields that
  could contain credentials.
