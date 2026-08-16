---
name: geist-pet-creator
description: Create, validate, repair, audit, export, or locally install Geist-compatible animated Pet bundles. Use for Geist Pet concepts, character bibles, identity blending, approved image candidates, alpha PNG sprite frames, anatomy-drift QA, pet.json metadata, spritesheet.webp export, and cost-accounted image generation.
---

# Geist Pet Creator

Build Geist-compatible Pets from individual `192x208` alpha PNG frames. Treat
those frames as durable source; generated strips and exported atlases are not
source. Fail closed when identity, layout, alpha, motion, cost authority, or an
approval gate is unresolved.

## Initialize the runtime

Resolve this skill directory as `SKILL_DIR`, then check the isolated runtime
before running any bundled Python tool:

```bash
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" check
```

If it is absent or stale, tell the user:

- Pillow 12.3.0 will be downloaded from PyPI;
- it will be installed only in the Geist Pet Creator cache runtime;
- system Python, Pet bundles, and installed Pets will not be modified;
- no `sudo` is used.

Ask for approval before the first download. After approval, run `install`; use
`repair` for a stale runtime. Never run either command silently.

```bash
python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" install
PET_PYTHON="$(python3 "$SKILL_DIR/scripts/bootstrap_runtime.py" python)"
```

Supported hosts are macOS and Linux with Python 3.11-3.14. Treat Windows as
experimental. Use `"$PET_PYTHON"` for every Python command below.

## Choose two independent modes

### Drawing mode

Choose once when the bundle is created and record it in the bundle provenance.
Do not mix drawing modes after the first candidate.

- **Built-in image generation**: use the running agent's image capability.
- **External provider**: use `scripts/generate_candidates.py` with OpenRouter
  configuration from `imagegen.json` and `OPENROUTER_API_KEY` from the
  environment.

Read [references/image-providers.md](references/image-providers.md) before an
external request.

### Workflow profile

Use **Quick** unless the user explicitly chooses another profile.

| Phase | Quick (default) | Studio | Full Automation |
| --- | --- | --- | --- |
| Concept sheet, when routed | human chooses | human chooses | human chooses |
| Canonical base | human chooses among up to 3 | human chooses among up to 3 | agent chooses among up to 3 |
| Nine animation states | agent promotes 1 candidate/state | human chooses among 3/state | agent promotes 1 candidate/state |
| Generative repair | agent, maximum 2 passes/frame | human chooses | agent, maximum 2 passes/frame |
| Final atlas audit | human approves | human approves | human approves |
| Local installation | separate explicit request | separate explicit request | separate explicit request |

Map profile decisions to generator flags per action:

- human decision: `--mode supervised`
- agent decision: `--mode auto`

Profiles may be overridden for a named action, such as “Studio for idle only.”
Record the profile, mode, candidate ID, decision maker, and reason in
`qa/approvals.json`.

“Go”, “continue”, “looks good”, and “just do it” do not grant spending authority,
select a candidate, approve the final audit, authorize export, or authorize
installation. Full Automation requires explicit decision authority such as
“all design decisions are up to you.”

## Guard external spending and data transfer

Before every external-provider run, show one concise run summary with all of the
following and wait for explicit approval unless the user already granted
authority with equal or stricter ceilings for this run:

- provider and endpoint;
- exact model;
- images requested and cumulative images in this build pass;
- total estimated cost when known, `--max-images`, and the total
  `--max-cost-usd` ceiling;
- which local reference images and prompt content will be uploaded.

Do not itemize or require a per-image price breakdown. Obtain authority against
the total run ceiling.

Quick and Full Automation allow at most **64 generated images per normal complete
pass**, including base options and retries. Maintain the cumulative count from
`qa/spend.jsonl`; stop at 64. Studio has no implicit pass budget: calculate its
requested candidates, show the ceiling, and obtain authority first.

Every provider command must include explicit `--max-images` and
`--max-cost-usd`. Treat these as last-resort guards, not consent. The generator
appends each answered request immediately to bundle and user-level ledgers, so a
failed run remains accountable and resumable.

Read keys only from the environment. Never put a key in `imagegen.json`, a Pet
bundle, a command argument, a log, an approval record, or an export. The
generator rejects key-shaped bundle values.

The skill has no telemetry. Local validation, review, repair, and export make no
network calls. Upload art or prompts only for user-requested generation.

## Follow this workflow

1. Inspect the request and any existing bundle. Choose drawing mode and profile.
2. Define identity, personality, palette, props, motion, and the Part Manifest in
   `character-bible.md`.
3. When there are multiple characters or materially different design directions,
   generate one labeled concept sheet of at most 12 cells and stop for a human
   selection. This gate remains in Full Automation.
4. Generate a canonical base. Preserve enough safe-box headroom for motion.
5. Generate each animation state using the selected profile. Generate
   `running-right`; mirror it deterministically for `running-left` unless the user
   explicitly requests separately drawn left-facing art.
6. Normalize and promote only the selected candidate. Preserve rejected and raw
   files under `sources/`.
7. Validate all frames. Repair the smallest failing unit and revalidate.
8. Run the full anatomy audit. Deterministic repairs may be applied with backups;
   visible redraws re-enter the candidate gate. Stop after two failed repair
   passes for a frame and report the underlying bible/prompt problem.
9. Present `qa/final-audit.html`. Record a human approval bound to the exact
   `atlas_digest`.
10. Export only after that approval. Install only on a separate explicit request.
11. Audit the exported WebP again to catch encoding damage.

Read [references/generation-workflow.md](references/generation-workflow.md) for
candidate packet structure and [references/qa-rubric.md](references/qa-rubric.md)
for approval criteria.

## Preserve the Geist contract

The atlas is `1536x1872`: 8 columns by 9 rows, each cell `192x208`.

| Row | State | Source frames |
| ---: | --- | ---: |
| 0 | idle | 6 |
| 1 | running-right | 8 |
| 2 | running-left | 8 |
| 3 | waving | 4 |
| 4 | jumping | 5 |
| 5 | failed | 8 |
| 6 | waiting | 6 |
| 7 | running | 6 |
| 8 | review | 6 |

All 15 unused atlas cells must remain transparent. Use numeric filenames
`000.png`, `001.png`, and so on. Validate exactly the required count for each
state. Read [references/contract.md](references/contract.md) before changing
metadata, state ordering, filenames, or export structure.

Required bundle shape:

```text
PetName.pet/
  pet.json
  character-bible.md
  imagegen.json                 # external provider only
  sources/
    canonical-base.png
    candidates/<candidate-id>/
    references/
    raw/
  frames/<state>/000.png
  qa/
    approvals.json
    spend.jsonl
    validation.json
    final-audit.json
    final-audit.html
  final/
    pet.json
    spritesheet.webp
```

## Lock identity before animation

Every Pet uses the Geist house form:

- one legless, rounded floating body;
- one thick Sky outline around a Cream body area;
- two dot eyes and a tiny mouth;
- exactly one centered Mango heart;
- flat fills, no shadows or gradients;
- attached, readable props;
- simple geometry that survives `192x208`.

For an existing character, mascot, or recognizable object, identify four to six
high-information cues. Translate them into Geist geometry without copying the
source rendering style. House-form invariants outrank identity cues; identity
cues outrank decorative detail. Read
[references/identity-blend.md](references/identity-blend.md) and attach
`assets/geist-house-style.jpg` as the house-form reference.

Reject both failure directions:

- **source copy**: source anatomy/rendering wins and Geist form disappears;
- **generic blob**: Geist form remains but the source is no longer nameable.

Write the retained and dropped cues in an `## Identity Blend` table. Add every
countable anatomy cue to the Part Manifest:

```markdown
## Part Manifest

| Part | Count | Side | Attachment | Notes |
| --- | --- | --- | --- | --- |
| wing | 1-2 | left, right | shoulder | One may hide side-on |
| beak | 1 | center | face | Never duplicated |
| eye | 2 | left, right | face | Never duplicated |
```

## Generate and review candidates

External-provider examples:

```bash
"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action canonical-base --variants 3 --mode supervised \
  --max-images 6 --max-cost-usd 0.25

"$SKILL_DIR/scripts/with_openrouter_key.sh" "$PET_PYTHON" \
  "$SKILL_DIR/scripts/generate_candidates.py" /absolute/path/PetName.pet \
  --action waiting --variant a --mode auto \
  --max-images 14 --max-cost-usd 0.50
```

For Studio, run state variants `a`, `b`, and `c` separately with
`--mode supervised`; each must have a distinct `--variant-intent`. Do not call
three identical prompts “options.”

Pre-screen every packet for identity, Part Manifest counts, house form,
transparent background, safe padding, registration, and loop continuity. Never
show known failures as choices.

Render the review page:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/render_candidate_review_html.py" \
  /absolute/path/PetName.pet --action waiting \
  --output /absolute/path/PetName.pet/qa/waiting-review.html
```

Promote by exact candidate ID. A human-gated action needs an explicit selection
such as `waiting-b`; a vague approval is insufficient.

## Validate, audit, and export

Validate without changing visible art:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/validate_source_bundle.py" \
  /absolute/path/PetName.pet \
  --json-out /absolute/path/PetName.pet/qa/validation.json
```

Deterministic fixes may clear transparent RGB residue or repair simple fringe,
but preserve backups and rerun validation.

Audit every frame and build the final review:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/audit_spritesheet.py" \
  /absolute/path/PetName.pet --repair
```

Suspicion scores prioritize review; they never prove anatomy correctness. Add
agent verdicts for every readable Part Manifest item, then verify them:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/audit_spritesheet.py" \
  /absolute/path/PetName.pet --verify-verdicts
```

After the human approves `qa/final-audit.html`, append an approval record with:

- `approved_action: "final-audit"`
- `decision: "approved"`
- the exact `atlas_digest`
- approver and timestamp

Export refuses a missing or stale digest even with `--force`:

```bash
"$PET_PYTHON" "$SKILL_DIR/scripts/export_geist_pet.py" \
  /absolute/path/PetName.pet \
  --output-dir /absolute/path/PetName.pet/final

"$PET_PYTHON" "$SKILL_DIR/scripts/audit_spritesheet.py" \
  /absolute/path/PetName.pet --mode post-export
```

Use `--install` only when explicitly requested. Never delete a Pet bundle or an
installed Pet while removing or repairing this skill's runtime.

## Bundled resources

- `references/contract.md`: source and export contract
- `references/generation-workflow.md`: prompts, candidates, promotion, repair
- `references/identity-blend.md`: Geist/source identity translation
- `references/image-providers.md`: provider configuration, model checks, ledgers
- `references/qa-rubric.md`: candidate and atlas QA
- `references/asset-guide.md`: bundled house-style reference and usage rights
- `scripts/bootstrap_runtime.py`: isolated dependency lifecycle
- `scripts/generate_candidates.py`: external generation with spend guards
- `scripts/validate_source_bundle.py`: deterministic frame validation
- `scripts/audit_spritesheet.py`: anatomy and atlas audit
- `scripts/export_geist_pet.py`: guarded Geist export and optional installation
