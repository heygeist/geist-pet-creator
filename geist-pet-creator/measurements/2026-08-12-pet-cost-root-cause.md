# Pet cost root cause — 2026-08-12

A source audit of the claims in `pet-design/PET-COST-FEEDBACK.md`, which reported $3.18 and 130
image calls for one Pet with 55% of spend discarded. Every verdict is traced to the skill's own
code, prose, or committed measurement — never to the field report.

This file follows the `measurements/` convention (dated findings doc, linked from SKILL.md §
References) but carries no companion `.json`: it audits source, not a run.

**Two states of the tree.** The report describes commit `c9bf4b7`, and that is what the verdict
table below judges. While this audit was running, an uncommitted change landed in the working tree
(`scripts/generate_candidates.py`, `scripts/geist_house.py`, `references/image-providers.md`,
mtimes 21:05–21:09) implementing report fixes 1, 2, 3 and 5. § "State of the fix" checks that work
line by line and says which findings it closes and which survive. Line numbers are marked
`@c9bf4b7` or `@worktree`; paths are relative to `geist-pet-creator/geist-pet-creator/` unless
prefixed `pet-design/`.

## Verdicts (against `c9bf4b7`, the state the report describes)

| # | Claim | Verdict | Primary citation |
| --- | --- | --- | --- |
| 1a | `generate_frame()` asks transparent optimistically, then falls back to chroma | **confirmed** | `scripts/generate_candidates.py:604-658` @c9bf4b7 |
| 1b | Shipped `imagegen.json` template sets `"background": "transparent"` | **confirmed** | `references/image-providers.md:27-34` @c9bf4b7; code default `:195,240` |
| 1c | `openai/gpt-image-2` is the skill's documented default | **confirmed** | `scripts/generate_candidates.py:124` @c9bf4b7; `SKILL.md:37` |
| 1d | `gpt-image-2` rejects `background` with HTTP 400 | **behaviour confirmed; the quoted string is misattributed** | `measurements/2026-08-12-provider-eval.json` — `alpha_path: params-dropped+chroma`, `calls: 2`, 4/4 cases. The quoted 400 text on disk belongs to `gpt-5.4-image-2` (`provider-eval/results.json`) |
| 1e | The double call repeats on *every* frame — no memo | **confirmed, and worse than described** | `:638` @c9bf4b7 rebinds `config` **locally**; call site `:1312` inside loop `:1300` passes the untouched outer `config` every time. Three HTTP requests, two billed, per frame |
| 2a | The "no legs" rule never reaches the model's prompt | **confirmed** | rule `SKILL.md:256`; frame prompt `:680-692` @c9bf4b7 omits it |
| 2b | The framing-margin rule never reaches the prompt | **partly refuted** — an unquantified version does reach it | `:688` @c9bf4b7 |
| 2c | The flat-background rule never reaches the prompt | **partly refuted** — a flat-chroma line reaches it, and contradicts the line above it | `:158-161` vs `:689` @c9bf4b7 |
| 3a | Edge-contact / area-delta / opaque-fraction checks already exist as callable code | **confirmed** | `fit_report` `:460-476`; `measure_cell` `audit_spritesheet.py:116-157`; `alpha_is_real` `:548-563` |
| 3b | No partial-run gate before a full state is drawn | **confirmed** — the check runs per frame and is recorded, never acted on | `:1319-1321` @c9bf4b7 (append to `misfits`, no `break`) |
| 4 | SKILL.md mandates ≥3 variants per action, enforced in prose only | **confirmed for sprite actions, refuted for `canonical-base`** | prose `SKILL.md:207`, `references/generation-workflow.md:164`; code enforces 3 at `:1240-1244` @c9bf4b7 |
| 5 | Bounding-box / headroom data already computed somewhere | **confirmed, in four places** | `CellTransform.from_reference` `:429-449`; `fit_report` `:460-476`; `measure_cell` `audit_spritesheet.py:135-143`; `alpha_bbox` `geist_pixels.py:36-38`. `render_candidate_review_html.py` computes **no** geometry at all |
| 6a | `audit_approval()` conflates absent with unreadable | **confirmed** | `scripts/export_geist_pet.py:63-78`, message `:152-159` |
| 6b | `audit --repair` does not repair `cell_bleed` | **partly** — it has a `cell_bleed` path, translation-only, structurally unable to fix the size-driven case the pipeline produces | `scripts/audit_spritesheet.py:243-259` |
| 6c | Chroma fringe cleanup absent; `alpha > 16` misses spill at 9–16 | **confirmed** | no fringe `--fix` anywhere; rule `validate_source_bundle.py:46-48,171-179`; `geist_pixels.py:20` sets `ALPHA_THRESHOLD = 8` |
| 7 | "The budget is right" ($1.33 for a clean pass) | **refuted** | `$1.33 = 57 ×` the **two-billed-call** median, `measurements/2026-08-12-provider-eval.json` `summary[0]` |
| 8 | "$2.70 saved on this Pet alone" | **unverified** | the shipped ledger recorded 15 of the claimed 130 calls, `pet-design/KarateCrownGuardian.pet/qa/spend.jsonl` |

---

## 1. The alpha capability gate

### The code path, quoted (`:604-658` @c9bf4b7)

```python
    alpha_path = "native"
    try:
        image, cost = once(config, prompt)
    except SystemExit as error:
        # ... openai/gpt-image-2 answers "background: not
        # supported. Accepted: auto, opaque" ...
        if "400" not in str(error) or "parameter" not in str(error).lower():
            raise
        config = ProviderConfig(..., output_format=None, background=None, ...)
        image, cost = once(config, prompt)
        alpha_path = "params-dropped"

    if not require_alpha:
        alpha_path = "opaque by request"
    elif not alpha_is_real(image):
        image, cost = once(config, prompt + CHROMA_SUFFIX)
        image = key_out_chroma(image)
        alpha_path = "chroma-key fallback" if alpha_path == "native" else "params-dropped+chroma-key"
```

On the default model that is **three HTTP requests and two billed calls per frame**: a free 400, a
billed opaque image discarded in full, and a billed chroma image kept. The report's "two calls" is
right about the money and understates the latency by one round trip.

### There is no memo, and there could not be one

The reassignment at `:638` binds a **local** name. The caller's `config`, built once at `:1254` and
handed to the frame loop at `:1312`, is never touched, so the loop at `:1300-1328` repeats the whole
400 → params-drop → opaque → chroma dance on every frame of every state for the life of the process.
Confirmed by the ceiling arithmetic, which was sized *for* the repeat: `:1250` reads
`default_images = args.variants * 2  # room for one transparency retry each`, and
`references/image-providers.md:344,349` @c9bf4b7 documents the doubling as expected.

### The default and the template

`DEFAULT_MODEL = "openai/gpt-image-2"` (`:124`, restated `SKILL.md:37`). The documented template
(`references/image-providers.md:27-34` @c9bf4b7):

```json
{ "provider": "openrouter", "model": "openai/gpt-image-2",
  "output_format": "png", "background": "transparent" }
```

and the code defaults `background: str = "transparent"` (`:195`) and
`raw.get("background", "transparent")` (`:240`). The documented default configuration is guaranteed
to 400 on the documented default model.

### Provider evidence

I did not spend the user's credit on a fresh probe. Two on-disk primary artefacts settle it:

1. `measurements/2026-08-12-provider-eval.json` — committed probe data. All four
   `openai/gpt-image-2` attempts record `"alpha_path": "params-dropped+chroma"`, `"calls": 2`. That
   branch is reachable **only** when the first request raised a 400 whose body contained the
   substring `parameter` (`:636`; mirrored at `scripts/eval_providers.py:582-583`). The rejection is
   measured, not asserted.
2. `provider-eval/results.json` — an uncommitted eval output holding a raw captured body:

   > `HTTP 400: {"error":{"message":"No provider for openai/gpt-5.4-image-2 supports the requested parameter(s): output_format \"png\", background \"transparent\", n \"1\". Provider rejections: OpenAI: background: not supported. Accepted: auto, opaque","code":400}}`

   Note the model id. That exact string belongs to **`openai/gpt-5.4-image-2`**. The report and
   `pet-design/KarateCrownGuardian.pet/imagegen.json` both attribute it to `gpt-image-2`. The
   behaviour is confirmed for `gpt-image-2` by (1); the quotation is not, by anything on disk.

### The reference fix

`pet-design/KarateCrownGuardian.pet/tools/generate_frames.py:49-88` monkey-patches
`gc.generate_frame` with a one-call direct-chroma version gated on
`NO_ALPHA_MODELS = {"openai/gpt-image-2"}` (`:49`). It adds one thing the skill lacks: a post-key
verification (`:68-75`) refusing a frame whose keying produced no usable alpha. See M2.

---

## 2. Prompt prohibitions: where the rules live and where they stop

The rules exist and two of the three were **already codified as constants**. This was never a
prose-to-prompt problem; it was one prompt builder out of three omitting constants the other two
already used.

`scripts/geist_house.py:22-29` — `HOUSE_FORM`, containing "no legs, no feet, no knees, no shoes, no
floor plane, no cast shadow, no detached effect". `scripts/geist_house.py:32-39` —
`NEVER_TRANSFERS`, opening "legs, feet, knees, shoes, …".

| Prompt builder @c9bf4b7 | `HOUSE_FORM` | `NEVER_TRANSFERS` |
| --- | --- | --- |
| `build_sheet_prompt` `:721-764` | yes, `:749` | yes, `:762` |
| `build_base_prompt` `:767-800` | yes, `:789` | yes, `:798` |
| **`build_prompt` — all 57 frames — `:680-692`** | **no** | **no** |

The whole frame prompt (`:680-692` @c9bf4b7):

```python
        f"Draw frame {index} of {frame_count} for the `{state}` sprite action of this Pet.\n"
        f"The attached images are the identity lock: image 1 is the canonical base, "
        f"image 2 is the previous approved frame of this same action.\n"
        f"Keep the silhouette, proportions, palette, face landmarks, props and scale identical to them.\n"
        f"Motion read: {variant_intent}\n"
        f"Compose the whole body inside the frame with clear margin on all four sides. "
        f"Transparent background. One character only, no shadow, no ground marks, no detached effects, "
        f"no text.{manifest.prompt_block()}\n"
        f"{extra}"
```

- **No legs — confirmed missing.** Rule at `SKILL.md:256` and
  `references/generation-workflow.md:389-390`. Neither the state name nor `build_prompt` carries it.
  The only route in was `--extra-prompt` (`:1199`), typed by hand, per state, from memory of a
  reference file, with nothing verifying it happened.
- **Framing margin — partly refuted.** `:688` does say "Compose the whole body inside the frame with
  clear margin on all four sides." Absent: the number, and the report's real insight — *make the
  motion smaller rather than moving the character*.
- **Flat background — partly refuted, plus a defect the report did not name.** `CHROMA_SUFFIX`
  (`:158-161`) does say "flat, uniform chroma-key background of pure green (#00FF00)". But it is
  *appended* to a prompt that already said "Transparent background." (`:689`), so the model received
  two contradictory background instructions in one string — and it forbade green *on the character*
  while never forbidding a panel, box, card, border or backdrop, which is the exact shape of the
  "unkeyed background" failure the report priced at $0.16.

`manifest.prompt_block()` (`scripts/geist_manifest.py:59-67`) does reach the frame prompt, so the
Part Manifest travelled. The house form and the never-transfer list did not.

---

## 3. Pre-flight: the checks existed, the gate did not

| Check | Function | Location |
| --- | --- | --- |
| edge contact | `measure_cell` → `CellMeasurement.edge_contact` | `scripts/audit_spritesheet.py:135-143` |
| safe-padding fit under the run transform | `CellTransform.fit_report` | `:460-476` @c9bf4b7 |
| area / bbox / asymmetry / diff vs anchor | `audit_atlas` `signals` | `scripts/audit_spritesheet.py:360-369` |
| opaque fraction / clear border | `alpha_is_real` | `:548-563` @c9bf4b7 |
| bbox of visible pixels | `alpha_bbox` | `scripts/geist_pixels.py:36-38` |

And the gate was genuinely absent (`:1319-1321` @c9bf4b7):

```python
        fit = transform.fit_report(cell, args.safe_padding)
        if not fit["fits"]:
            misfits.append({"frame": index, **fit})
```

The defect is detected on the frame that shows it and appended to a list only printed after the
whole state finished (`:1349`). No `break`, no threshold, no flag. An 8-frame state whose frame 1
already failed drew seven more at full price and then reported all of them.

`--frames 0-1` existed (`:1182`, `parse_frame_range` `:1016-1026`), so a two-frame pre-flight was
*expressible*. Nothing in `SKILL.md` or `references/` said to use it that way — the only mention of
`--frames` outside the parser is `references/image-providers.md:292`, a single-frame repair example.
The skill ships no calibration or smoke path for a Pet build at all.

---

## 4. Variant policy: prose for states, code for the base

Prose, `SKILL.md:207`:

> For each sprite action under supervised mode, provide at least 3 distinct candidate variants unless the human asks for a different count. Full automation provides one.

Restated at `SKILL.md:57,108`, `references/generation-workflow.md:164`, and as a review rejection
criterion at `references/qa-rubric.md:58`.

- **Sprite actions: prose only.** There is no `--variants` for a state action. `--variant` (`:1180`)
  is a single letter that becomes part of the candidate id. Three variants means invoking the script
  three times. Nothing counts them; nothing refuses a promotion made from one.
- **`canonical-base`: enforced in code** (`:1240-1244` @c9bf4b7):

```python
    if args.variants is None:
        args.variants = 1 if args.cell_image else 3
```

This corrects the report, which proposes "invert the default; keep the 3-variant rule for
`canonical-base`". That is already the code's shape. What is missing is the pre-screen gate
(§3) and prose for the sprite actions — the base rule needs no work.

---

## 5. Motion headroom: already computed, and the transform guaranteed there was none

`canonical-base-review.html` comes from `scripts/render_candidate_review_html.py`. Grepped for
`bbox`, `alpha_bbox`, `headroom`, `safe_padding`, `CELL_WIDTH`, `CELL_HEIGHT`: **it computes no
geometry at all.** It renders packets. So the figure was missing from the page — but it never needed
computing.

The function to expose is `CellTransform.from_reference` (`:429-449` @c9bf4b7):

```python
        margin = (safe_padding + RESAMPLE_BLEED) * 2
        scale = min((CELL_WIDTH - margin) / body_width, (CELL_HEIGHT - margin) / body_height)
```

It already knew the 192×208 cell (`geist_grid.py:14-15`), the margin, and the body's bounding box.
`run_canonical_base` (`:1141-1148`) already called it per variant, already ran `fit_report`, already
wrote `record["fits_safe_padding"]` and `candidates_outside_safe_padding` (`:1161`). The review page
just never read any of it.

**The deeper finding is that the number would have read ~0 for every base, by construction.** That
formula scaled the body to *maximally fill* the cell minus `safe_padding + RESAMPLE_BLEED` = 7px on
its binding axis. Frame 0 landed with exactly 7px of clearance, and every later frame reused the
identical scale (`:1315-1317`, the one-transform-one-run rule). Any pose exceeding frame 0's bbox by
more than 7px bled — 3.6% of cell width — while `unsafe_bounds`
(`validate_source_bundle.py:136-141`, default padding 4) fires at 3px.

So the "long flaring hair" the report blames is second-order. The first-order cause was that the
skill's own transform allocated **zero motion headroom**, and motion is what the other 56 frames are
for. (The worktree change fixes exactly this — see below.)

---

## 6. The three bugs

### 6a. `audit_approval()` — confirmed exactly as described

`scripts/export_geist_pet.py:63-78`:

```python
def audit_approval(bundle: Path, digest: str) -> dict[str, Any] | None:
    approvals_path = bundle / "qa" / "approvals.json"
    if not approvals_path.is_file():
        return None
    try:
        approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for entry in approvals if isinstance(approvals, list) else []:
        ...
    return None
```

Four distinct states collapse into one `None`: absent (`:65-66`), unparseable (`:69-70`), parseable
but not a top-level list (`:71`), and correct but no matching digest. The caller prints one message
for all four (`:152-159`, "no approved final anatomy audit for these exact frames") naming the
*fourth*. A malformed-shape approvals file therefore sends the reader hunting for an approval that is
present. Unfixed in the worktree.

### 6b. `audit --repair` and `cell_bleed` — partly

It has a `cell_bleed` path; that path is structurally incapable of fixing the case this pipeline
produces. `scripts/audit_spritesheet.py:243-259`:

```python
    if measurement.edge_contact and measurement.bbox:
        left, top, right, bottom = measurement.bbox
        shift_x = 0
        shift_y = 0
        if left < safe_padding:
            shift_x = safe_padding - left
        elif right > CELL_WIDTH - safe_padding:
            shift_x = (CELL_WIDTH - safe_padding) - right
```

1. **Translation only, never a rescale.** A sprite wider than `192 − 2·padding` or taller than
   `208 − 2·padding` cannot be moved inside; no offset exists. Given §5 — frame 0 fitted to the cell
   minus 7px — an over-size frame is precisely the bleed the pipeline generates.
2. **Opposing edges.** With `left <= 0` *and* `right >= 192` the `if/elif` takes the `left` branch
   and shifts the sprite **further off the right edge**, then reports
   `"shifted the body +4,+0 back inside 4px safe padding"` (`:259`), consumes a repair pass, and the
   re-audit at `:820-821` still finds `cell_bleed`.
3. **A queued frame burns a pass without drawing anything.** `:732` sets `log[path] = passes + 1` in
   the *generative* branch. Two `--repair` runs that produced no art exhaust the 2-pass budget
   (`MAX_REPAIR_PASSES = 2`, `:36`) and the frame is silently skipped thereafter (`:705-707`).

`pet-design/KarateCrownGuardian.pet/tools/refit_state.py:57-103` is the correct fix in executable
form: one shared scale per state from the **union** bounding box across all its frames (`:64-72`),
applied identically to every frame (`:94-102`), preserving relative motion, deterministic, no
provider call, explicitly aware of the one-transform-one-run rule (`:14-15`). It belongs in
`deterministic_repair` as the fallback when translation cannot help. Unfixed in the worktree.

I could not reproduce the report's specific "six hard `cell_bleed` errors, zero deterministic
repairs": `qa/final-audit.json` is the post-fix state (`ok: true`, zero hard errors) and
`qa/repair-log.txt` holds no `cell_bleed` lines. The verdict is on the mechanism, from source.

### 6c. Chroma fringe cleanup — confirmed, including the threshold discrepancy

The validator's rule, `scripts/validate_source_bundle.py:46-48`:

```python
def is_green_fringe(red: int, green: int, blue: int) -> bool:
    """Green matte residue: bright green that dominates both other channels."""
    return green >= 180 and red <= 90 and green > blue * 1.25
```

applied (`:62-83`) to **boundary** pixels only (`boundary_mask`, `geist_pixels.py:41-48`) below
`OPAQUE_THRESHOLD` (245, `geist_pixels.py:23`), gated at `:171-179` on
`fringe >= 8 and fringe/edge >= 0.03` (`:26-27`).

There is **no fix for it anywhere in the skill**: `validate_source_bundle.py` offers only
`--fix-transparent-rgb` (`:268-272`) and `--detect-cyan-fringe` (`:273-277`), and
`audit_spritesheet.deterministic_repair` (`:220-261`) touches no colour on boundary pixels.

The threshold discrepancy is confirmed at the module — `geist_pixels.py:19-20`:

```python
# A pixel counts as visible above this alpha. Written once; imported everywhere.
ALPHA_THRESHOLD = 8
```

A cleanup using `alpha > 16` skips 9–16 entirely, which is inside the validator's visible band and
below its opaque cutoff: exactly the population the gate counts. The reference implementation records
the same trap in its header (`pet-design/KarateCrownGuardian.pet/tools/clean_chroma_fringe.py:32-41`)
and fixes it by importing `ALPHA_THRESHOLD`, `OPAQUE_THRESHOLD` and `boundary_mask` from
`geist_pixels` (`:41`), then reproducing `is_green_fringe` verbatim (`:65-66`). One caveat: it then
shadows the imported `OPAQUE_THRESHOLD` with a local `250` at `:62`, so it is not quite the
single-source-of-truth its docstring claims. Unfixed in the worktree.

---

## State of the fix (uncommitted worktree, 2026-08-12 ~21:05–21:09)

Three files changed: `scripts/generate_candidates.py` (+315/−57), `scripts/geist_house.py` (+36),
`references/image-providers.md` (+33/−9). Verified line by line.

**Closed.**

| Finding | How | Citation @worktree |
| --- | --- | --- |
| 1a/1e — optimistic double call | `ALPHA_PATHS` keyed on model id; `chroma-bare` asks for green on the **first** call | `generate_candidates.py:175-183`, `:713-806`. `ALPHA_PATHS` covers exactly `KNOWN_MODELS` (verified by import: symmetric difference empty), and `ALPHA_PATHS["openai/gpt-image-2"] == "chroma-bare"` |
| 1b — template 400s | `background` key removed from the documented template | `references/image-providers.md:28-34` |
| 2a — no-legs never reaches the model | `LEGLESS_MOTION` constant, injected for `MOTION_STATES` | `geist_house.py:59` and `:75`; injected at `generate_candidates.py:819,825` |
| 2b — margin unquantified | `FRAMING` states 15% on all four sides **and** "make the motion smaller and leave the character where it is" | `geist_house.py:52`; used at `generate_candidates.py:826` and in `build_base_prompt` `:930-932` |
| 2c — contradictory background lines | `build_prompt` no longer names a background at all; `generate_frame` appends exactly one of `CHROMA_SUFFIX` / `TRANSPARENT_SUFFIX`, both carrying `FLAT_FIELD` (which now bans panel/box/card/border/frame/vignette/backdrop) | `geist_house.py:67`; `generate_candidates.py:217-221`, `:740-758` |
| 3b — no partial-run gate | `preflight_problems()` vetoes the state after each of the first `PREFLIGHT_FRAMES` (2) frames on edge contact, opaque fraction, or ±35% area drift | `generate_candidates.py:1161-1186`, `:1529-1533` |
| 5 — zero motion headroom | `MOTION_HEADROOM = 0.08`; `from_reference` now scales `fitted * (1 - headroom)`; `--motion-headroom` flag added | `generate_candidates.py:204-215`, `:491-517`, `:1383-1388` |
| 5 — headroom not surfaced | `CellTransform.growth_allowance()` written into every canonical-base packet as `record["growth_allowance"]` and into the run result | `generate_candidates.py:518-534`, `:1318-1345` |

**Still open after the fix.**

1. **`growth_allowance` is computed but still not displayed.**
   `scripts/render_candidate_review_html.py` is unmodified and contains zero occurrences of
   `growth_allowance`. The number now exists in `candidate-context.json` and in stdout; the
   canonical-base review page — the one surface the report asked for — still does not show it.
2. **The chroma-first path never verifies its own key.** `generate_candidates.py:776-784` @worktree:

   ```python
       if chroma_first:
           image = key_out_chroma(image)
       elif require_alpha and not alpha_is_real(image):
   ```

   No `alpha_is_real` check on the keyed image, and the `elif` that would have run one is now
   unreachable for every model in `ALPHA_PATHS` — i.e. for all seven `KNOWN_MODELS`. Pre-flight
   catches it on frames 0–1 only; frames 2–7 of every state are written unverified. The reference
   implementation does check (`generate_frames.py:68-75`).
3. **A pre-flight abort exits 0.** `main()` prints `"ok": aborted is None`
   (`generate_candidates.py:1561`) and returns; there is no `raise SystemExit(1)`
   (`:1582-1587`). A driver loop like `pet-design/KarateCrownGuardian.pet/tools/run_all_actions.sh`
   that branches on exit status will treat an aborted state as a success and continue to the next.
4. **Five of nine states carry no leg prohibition.** `MOTION_STATES` is
   `{running-right, running-left, running, jumping}`; `failed`, `idle`, `review`, `waiting` and
   `waving` get no `LEGLESS_MOTION`. The comment justifies this ("the states whose NAME pulls
   hardest towards legs"), which is reasonable — but `HOUSE_FORM`, which also bans legs, is still
   absent from `build_prompt` entirely, so those five states carry no legless instruction at all.
5. **`ALPHA_PATHS` and `KNOWN_MODELS` must be kept in sync by hand.** They agree today. Nothing
   asserts it, and a model added to one and not the other silently changes behaviour — a
   `KNOWN_MODELS` entry missing from `ALPHA_PATHS` reverts to the expensive optimistic path.
6. **`ProviderConfig.background` still defaults to `"transparent"`.**
   `generate_candidates.py:255` and `load_config` `:300` @worktree. Harmless for table-listed models
   (the config is rebuilt by `drop_transparency_params`), but the doc now says `ALPHA_PATHS` decides
   the background while the dataclass still carries a contrary default.
7. **`build_base_prompt` restates the 15% margin by hand** (`generate_candidates.py:929-932`) instead
   of using the new `FRAMING` constant that `build_prompt` uses (`:826`). Two copies of one rule is
   the drift `geist_house.py`'s own docstring exists to prevent (`:2-8`).
8. Findings **6a**, **6b**, **6c**, **M1**, **M3**, **M4**, **M5**, **M7** below are untouched.

---

## Causes the report missed

### M1. The $1.33 "budget" already contains the doubled call

The report's framing — "the shipped art came to $1.28, almost exactly the $1.33 that `AGENTS.md`
budgets for a clean 57-frame pass. The budget is right." — does not survive the source of that
number. `measurements/2026-08-12-provider-eval.json`, `summary[0]`:

```
model openai/gpt-image-2 · median_cost_usd 0.023349 · projected_pass_usd 1.3309
alpha_paths ["params-dropped+chroma"]
```

and every one of its four attempts records `"calls": 2`. The $1.33 is `57 × 0.023349` where
`0.023349` is the **sum of both billed calls**. `pet-design/AGENTS.md:76-77` and `SKILL.md:91`
(which quotes $1.31) both present it as the cost of a clean pass. It is not: it is a budget for the
waste, and matching it is not evidence of a healthy build. Both figures need re-deriving now that
the one-call path exists.

### M2. Nothing verifies the chroma key before the frame is written

@c9bf4b7 `generate_frame` keyed and returned (`:656-658`) with no `alpha_is_real` re-check and no
check that `key_out_chroma` removed anything. If the model drew a panel, card or gradient, or a green
outside `KEY_TOLERANCE = 72` (`:163`), the frame entered the packet with its background baked in and
surfaced only at `validate_source_bundle` — after the whole state was paid for.

Worse, that failure poisoned the whole state: `CellTransform.from_reference` is built from frame 0
(`:1315-1316`). If frame 0's key failed, `alpha_bbox` covers the entire canvas, the derived `scale`
shrinks the full provider canvas into one cell, and **every remaining frame inherits that wrong
scale**.

The worktree change makes this *more* load-bearing, not less — see "Still open" item 2.

### M3. `running-left` is drawn from the provider with nothing stopping it

`SKILL.md:108,256` and `references/generation-workflow.md:390` say `running-left` should be a
deterministic horizontal flip of the approved `running-right` row. I grepped the whole `scripts/`
tree for `flip`, `mirror`, `transpose`, `FLIP_LEFT_RIGHT`: **there is no flip helper in the skill.**
Meanwhile `running-left` is a first-class member of `FRAME_COUNTS` (`geist_grid.py:25`) and therefore
of `ACTIONS` (`generate_candidates.py:170` @c9bf4b7), so `--action running-left` draws all 8 frames
through the provider with no warning. At 8 frames × 3 supervised variants that is ~24 paid calls the
skill's own rule says should be zero — the largest structurally avoidable line item after the alpha
gate, and the report does not name it. Still open.

### M4. `--repair` spends provider money on an explicitly advisory score

`scripts/audit_spritesheet.py:702`:

```python
        if not (frame["hard_errors"] or frame["suspicion"] >= SUSPICION_FLAG or has_fragment):
            continue
```

`SUSPICION_FLAG = 45` (`:39`). The score is documented as advisory (`:178-181`, "Advisory only. A
low score never means a frame is correct"), yet crossing 45 with no hard error queues the frame for
**generative** repair. `suspicion_score` (`:182-189`) awards up to 40 points for `bbox_delta * 1.2`
alone, so a bounding box that moved 38px versus the anchor reaches the threshold on displacement by
itself — which is what a `jumping` or directional frame is *supposed* to do.

Observable in the shipped artefact. `pet-design/KarateCrownGuardian.pet/qa/final-audit.json` reports
`ok: true` with **zero hard errors**, and simultaneously:

```
"deterministic": [],
"generative_repair_queue": [
  {"path": "frames/running-right/01.png", "pass": 2, "passes_left": 0, "reason": "suspicion", "suspicion": 82},
  {"path": "frames/running-right/06.png", "pass": 2, "passes_left": 0, "reason": "suspicion", "suspicion": 45},
  {"path": "frames/running-left/01.png",  "pass": 2, "passes_left": 0, "reason": "suspicion", "suspicion": 82},
  {"path": "frames/running-left/06.png",  "pass": 2, "passes_left": 0, "reason": "suspicion", "suspicion": 45},
  {"path": "frames/jumping/01.png",       "pass": 2, "passes_left": 0, "reason": "suspicion", "suspicion": 57}]
```

Five correct frames queued for paid regeneration on displacement alone, two of them at exactly the
threshold, all five now at `passes_left: 0`. The queue should require a hard error, or the
`bbox_delta` term should be measured against the state's expected travel rather than a single anchor.
Still open.

### M5. Every frame call ships a 1254×1254 PNG as Image 1

`:1289` @c9bf4b7 resolves `canonical_uri = image_reference(canonical)` from
`sources/canonical-base.png` and attaches it to all 57 frame calls (`:1302`). In the audited bundle
that file is **1254×1254, 1,278,813 bytes** — roughly 1.7 MB base64-encoded, on every call.

The sprite-scale version already exists: `write_base_packet` (`:899`) writes `sprite-scale.png` at
192×208 beside the promoted candidate, and its docstring calls it "the size the naming test actually
has to survive". Nothing uses it as a reference.

This shows in the money. The provider eval sent one reference and measured ~$0.011 per call
($0.0233 over two); the real frame path sends two references and
`pet-design/KarateCrownGuardian.pet/qa/spend.jsonl` records $0.021–$0.031 for a **single** call.
Input-image size is a first-class cost term here and no measurement in the repo isolates it. Still
open.

### M6. The alpha fallback is gated on a substring of the provider's prose

`:636` @c9bf4b7 / `:761` @worktree — `if "400" not in str(error) or "parameter" not in
str(error).lower(): raise`, duplicated at `scripts/eval_providers.py:582-583`. It works only because
OpenRouter's current message happens to read "supports the requested parameter(s)". Under
`c9bf4b7` a wording change would have hard-failed every frame on the default model. The worktree's
model-id table demotes this to a fallback for unlisted models, which is the right shape — the
`eval_providers.py` copy is unchanged.

### M7. The spend ledger captured 15 of the ~130 calls

`pet-design/KarateCrownGuardian.pet/qa/spend.jsonl` holds 15 lines totalling **$0.3708**, all between
10:48 and 10:57 on 2026-08-12, all `running-right` and `running` frames at one call each. The home
ledger (`~/.geist/spend.jsonl`) holds the same 15 for this Pet.

The reason is structural: only `generate_candidates.py` writes to the ledger (`SpendGuard.record` →
`SpendLedger.record`, `:391-398`). The bundle's own `tools/generate_base_candidates.py` calls the
provider directly and constructs no `SpendLedger` — grepped for both `SpendLedger` and `ledger`,
neither appears. Concept-sheet spend, base-candidate spend, and every hand-rolled probe are therefore
invisible to `spend_report.py`.

`SKILL.md:335` promises the opposite ("reports what a Pet's art cost"), and `geist_spend.py:4-8`
justifies the ledger precisely as the record of *spend that produced no artifact*. Any bundle that
adds a `tools/` wrapper silently defeats it — which is why the report's $3.18 and 130 calls cannot be
reproduced from anything the skill wrote. Still open.

### M8. Frame prompts are re-derived from disk on every call

`build_prompt` (`:680-681` @c9bf4b7, `:817` @worktree) calls
`read_manifest(bundle / "character-bible.md")` per frame, re-reading and re-regexing the bible 8
times for an 8-frame state. No provider money. Listed only to close it out as *not* a cost sink.

---

## Open questions I could not settle from source

1. **The exact 400 body for `openai/gpt-image-2`.** The behaviour is confirmed from committed probe
   data (`alpha_path: params-dropped+chroma`, 4/4 cases). The literal string
   `"background: not supported. Accepted: auto, opaque"` is on disk only for
   `openai/gpt-5.4-image-2`. Settling it costs ~$0.01 via `--verify-model`, which needs the user's
   OpenRouter credential; I did not spend it.
2. **Whether OpenRouter's `/images` endpoint documents `background` support per model.** Not checked
   against first-party docs. I had no first-party source I could reach without reasoning from the
   catalog, which project memory and `SKILL.md:35-47` both say is not authoritative.
3. **The report's $3.18 / 130-call accounting.** Not reproducible: the shipped ledger holds 15 calls
   (M7). The per-bucket splits ($0.79 clipping, $0.22 legs, $0.16 unkeyed, $0.36 variants, $0.16
   calibration) are field observations with no on-disk artefact behind them.
4. **"Six hard `cell_bleed` errors, zero deterministic repairs."** Not reproducible —
   `qa/final-audit.json` is post-fix and the repair logs contain no `cell_bleed` lines. §6b is a
   verdict on the mechanism, not on that count.
5. **"$2.70 saved on this Pet alone."** Unverifiable, and it appears to double-count: it assumes all
   ~109 drawn frames would exist under both regimes, while fixes 2–5 exist precisely to stop 59 of
   them from being drawn at all.
6. **What the $0.16 "calibration / smoke runs" bucket was.** The skill ships no calibration or smoke
   path for a Pet build. `--verify-model` (`:292-322` @c9bf4b7) is the only documented probe, ~$0.01,
   logged as `kind: "verify-model"`. Neither the bundle nor the home ledger holds a single
   `verify-model` line for this Pet.
7. **Whether `key_out_chroma`'s `KEY_TOLERANCE = 72` is the right width.** No measurement in
   `measurements/` covers keying quality; the provider eval scores `alpha_is_real` only, before the
   key. This matters more now that the chroma path is the default and unverified (see "Still open"
   item 2).
8. **Whether the worktree change has been run against a live provider.** No new measurement file, no
   new ledger lines, and no `alpha_path: "chroma-key"`-only provenance exist on disk. The
   `2 calls / $0.059` figure in its comments is quoted from the field report, not from a run I can
   see.
