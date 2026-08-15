# Geist Pet Source Contract

Use this contract for source bundles created by `geist-pet-creator`.

## Domain Language

- Use **Pet** for the animated Geist character.
- Use **Pet Metadata** for `pet.json`.
- Use **Pet bundle** or **Pet source bundle** for creation artifacts.
- Use **Pet Override** only when discussing app-specific Pet choices.
- Use **part** for one named, countable, visible piece of the Pet: a body piece or an attached prop. A palette, a style, or a mood is not a part.
- Use **Part Manifest** for the table in `character-bible.md` that lists every part and how many times it may appear.
- Use **anatomy drift** for a frame that disagrees with the Part Manifest: a part missing, a part duplicated, or a part crossing the cell line.
- Use **derived Pet** for a Pet built from something already recognizable: a character, cast, mascot, brand figure, or known object or animal.
- Use **house form** for the Geist visual language every Pet shares, whatever its source.
- Use **identity cue** for one feature that makes a derived Pet's source nameable. A cue may or may not be a part.
- Use **Identity Blend** for the table in `character-bible.md` that records a derived Pet's ranked cues, their Geist translation, and the cues that were dropped.
- Use **anchor frame** for the frame a state's other frames are measured against.
- Use **suspicion** for the audit's attention ranking. Suspicion ranks which frames to look at. Suspicion never means a frame passed.
- Use **Built-in Image Generation** for the default mode, which draws with the agent's own image generation capability.
- Use **External Image Provider** for the additional mode, which draws through a configured HTTP provider.
- Use **Quick**, **Studio**, and **Full Automation** for workflow profiles. Drawing mode and workflow profile are independent.
- Avoid using "custom pet" as canonical wording.

## Source Bundle Layout

```text
PetName.pet/
  pet.json
  imagegen.json          # present only in External Image Provider mode
  character-bible.md
  sources/
    canonical-base.png
    candidates/
    references/
      geist-house-style.png        # required for a derived Pet
    raw/
      repair-backups/<state>/<index>-pass<n>.png
  frames/
    <state>/<index>.png
  qa/
    approvals.json
    spend.jsonl          # append-only, one line per provider call
    <sprite-action>-review.html
    final-audit.json
    final-audit.html
    repair-log.json
  final/
```

`frames/` is the durable source of truth. `sources/raw/` may contain high-resolution generations, strips, masks, or rejected attempts, but those files are not exported directly.

`sources/candidates/` contains generated art before approval. Candidate files are review artifacts, not source frames. A candidate becomes source truth only after agent pre-screening and an approval of that exact candidate id — from a human for a human-gated phase, or from the agent for a Quick/Full-Automation state decision — then normalization into `sources/canonical-base.png` or `frames/`.

`qa/spend.jsonl` is append-only and authoritative for what this Pet cost. Every provider call adds a line when the provider answers, so spend that produced no candidate packet is still recorded. Read it with `spend_report.py`; the schema is in [image-providers.md](image-providers.md) § The spend ledger.

Each sprite action must have its own approval before it enters `frames/`. Sprite actions are `canonical-base`, `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, and `review`. Approval for one action does not approve another action.

Directional movement note: `running-right` and `running-left` mean moving/gliding horizontally in the app, not literal running with legs. Create and approve `running-right` first; `running-left` should normally be the same source frames mirrored horizontally from the approved `running-right` row, with its own approval record. Do not use or approve feet, legs, foot-step poses, walking, jogging, sprinting, shoes, knees, or running mechanics for those directional rows.

`qa/<sprite-action>-review.html` is the human approval surface for each action. For animation states, it must render every passing variant as a moving sprite preview, not just as a static contact sheet. It must also contain exact prompts, pre-screen status, a **Choose** button that copies the selected candidate id, and a **Copy Prompt** button that copies the candidate prompt.

## Pet Metadata

Use `pet.json` in the source bundle:

```json
{
  "id": "rainy-geist",
  "displayName": "Rainy Geist",
  "description": "A blue hooded spirit with an orange heart.",
  "spritesheetPath": "spritesheet.webp"
}
```

The exporter writes a Geist-ready copy of this metadata beside the final spritesheet.

## Identity Blend Contract

A derived Pet's `character-bible.md` must carry an `## Identity Blend` section above the Part Manifest. It records which cues of the source survived the house form, so a later repair cannot quietly re-decide the blend.

Use this exact table shape:

```markdown
## Identity Blend

Source: <what it is, in plain words, without relying on a name>

| Rank | Source cue | Geist translation | Reads at 192x208 |
| --- | --- | --- | --- |
| 1 | forked silver storm crest | two broad rounded silver crest forks on the dome | yes, silhouette |
| 2 | indigo courier hood | one flat indigo crown panel with attached side tabs | yes, silhouette |
| 3 | brass message capsule | one thick rounded capsule attached at the side | yes, prop |
| 4 | pale lightning sash | one flat pale-yellow diagonal body panel | yes, color block |
| 5 | alert expression | raised dot eyes and a tiny determined mouth | yes, expression |

Dropped: boots and legs — house form. Loose paper — detached props. Chest badge — competes with the Mango heart.
```

Rank 1 is the cue that does most of the naming, normally the crown cue. Keep the table to 4-6 rows and to a single prop. The `Dropped` line is required, including its reasons.

Every countable cue also gets a Part Manifest row, so the anatomy audit counts it like any other part.

A derived Pet with no `## Identity Blend` section fails candidate pre-screen; it is not a warning-level gap, because the two locks cannot be checked against each other without it. Original Pets do not need the section.

A derived bundle also carries `sources/references/geist-house-style.jpg`, copied from `assets/geist-house-style.jpg` in the skill. The bundle holds its own copy so a packet stays reproducible after the skill moves or updates, and `inputs.json` must list it alongside the identity reference for every derived generation call.

Read [identity-blend.md](identity-blend.md) before filling it in, and [asset-guide.md](asset-guide.md) before using the bundled house-style reference.

## Part Manifest Contract

`character-bible.md` must carry a `## Part Manifest` section. The manifest is the list every frame is counted against, so anatomy drift becomes a countable difference instead of a feeling.

Use this exact table shape:

```markdown
## Part Manifest

| Part | Count | Side | Attachment | Notes |
| --- | --- | --- | --- | --- |
| head tuft spike | 3 | top | crown | Never duplicated |
| wing | 1-2 | left, right | shoulder | one wing hides behind the body in side-on poses |
| beak | 1 | center | face | Never duplicated |
| eye | 2 | left, right | face | Never duplicated |
| heart marking | 0-1 | center | chest | hidden when the body curls up |
| body | 1 | center | root | Never duplicated |
```

`Count` is one number, or a `min-max` range. Use a range for a part that a pose can legitimately hide: the low bound covers occlusion, and the high bound still catches duplication. Write `Never duplicated` in `Notes` for a part that must never appear more often than its high bound, whatever the pose.

A Pet source bundle with no `## Part Manifest` still audits, with a warning, against `sources/canonical-base.png`. Every bundle this skill creates gets a manifest.

## Final Audit Contract

Every frame of a finished Pet gets audited for anatomy drift before the Pet reaches anyone. The audit runs twice:

| Run | Reads | Gates | Human |
| --- | --- | --- | --- |
| Pre-export | `frames/` composed into an atlas in memory | export | approves `qa/final-audit.html` |
| Post-export | the written `final/spritesheet.webp` | delivery and install | interrupted only on mismatch |

The pre-export run gates export because an unaudited Pet should never produce a `final/` artifact at all. The post-export run exists because the WebP re-encode can damage alpha, and only that run sees the file that ships.

Coverage splits by what needs eyes:

- **57 artwork cells** — audited frame by frame against the Part Manifest by an agent and a human.
- **15 empty cells** — asserted transparent by script. Visible pixels there are a hard error.

`qa/final-audit.json` records one entry per artwork cell with `agent_verdict: null`. The agent fills every verdict in. `audit_spritesheet.py --verify-verdicts` exits non-zero while any verdict is still null, so a partly-audited Pet cannot pass as audited.

## Frame Contract

All normalized source frames must be alpha PNGs with this exact size:

- Cell size: `192x208`
- Mode: RGBA or PNG with alpha channel
- Background: transparent
- Sprite: complete, unclipped, inside safe padding

State rows:

| Row | State | Source frames | Atlas columns |
| --- | --- | ---: | --- |
| 0 | `idle` | 6 | 0-5 |
| 1 | `running-right` | 8 | 0-7 |
| 2 | `running-left` | 8 | 0-7 |
| 3 | `waving` | 4 | 0-3 |
| 4 | `jumping` | 5 | 0-4 |
| 5 | `failed` | 8 | 0-7 |
| 6 | `waiting` | 6 | 0-5 |
| 7 | `running` | 6 | 0-5 |
| 8 | `review` | 6 | 0-5 |

Unused atlas cells after each state's final frame must remain fully transparent.

## Approval Contract

Maintain `qa/approvals.json` when generated art is used. Every one of the ten sprite actions plus `final-audit` needs a decision record. Who made each decision depends on the decision mode, so every record carries `decided_by`, either `human` or `agent`.

Two of those decisions must carry `decided_by: "human"` whatever the mode: `final-audit`, which export enforces in code, and `concept-sheet` when the brainstorm route fired. A `final-audit` record written with `decided_by: "agent"` is invalid — it claims a human approved pixels nobody looked at.

The `final-audit` approval carries an `atlas_digest`, so an approval cannot outlive the artwork it approved. Change one pixel of one frame and the digest changes, which reopens the gate:

```json
{
  "candidate_id": "final-audit-22db90a8d97f",
  "approved_action": "final-audit",
  "approved_for": "final/spritesheet.webp",
  "atlas_digest": "22db90a8d97fbf6e42e31823a1e7edac602461e6c9b80bfcb63293343558f508",
  "source": "qa/final-audit.html",
  "decision": "approved",
  "decided_by": "human",
  "approver_note": "All 57 frames read correctly against the Part Manifest.",
  "decided_at": "2026-08-12T00:00:00Z"
}
```

Sprite-action approvals keep their existing shape:

```json
[
  {
    "candidate_id": "base-a",
    "approved_action": "canonical-base",
    "approved_for": "sources/canonical-base.png",
    "source": "sources/candidates/base-a/candidate.png",
    "prompt_file": "sources/candidates/base-a/prompt.md",
    "decision": "approved",
    "approver_note": "Use this as the identity lock.",
    "decided_at": "2026-07-05T00:00:00Z"
  },
  {
    "candidate_id": "waiting-b",
    "approved_action": "waiting",
    "approved_for": "frames/waiting/",
    "source": "sources/candidates/waiting-b/contact-sheet.png",
    "prompt_file": "sources/candidates/waiting-b/prompt.md",
    "decision": "approved",
    "decided_by": "human",
    "approver_note": "Chosen from waiting-a, waiting-b, and waiting-c.",
    "decided_at": "2026-07-05T00:10:00Z"
  }
]
```

An agent decision in Quick or Full Automation uses the same shape and adds why it won, because a choice with no stated reason cannot be reviewed later:

```json
{
  "candidate_id": "waiting-a",
  "approved_action": "waiting",
  "approved_for": "frames/waiting/",
  "source": "sources/candidates/waiting-a/contact-sheet.png",
  "prompt_file": "sources/candidates/waiting-a/prompt.md",
  "decision": "approved",
  "decided_by": "agent",
  "decision_mode": "auto",
  "ladder": {
    "deciding_level": "pre-screen",
    "ranking": ["waiting-a"],
    "reason": "single variant, pre-screen pass on all five checks; footprint within 2px of idle"
  },
  "regenerations": 0,
  "decided_at": "2026-08-12T10:47:59Z"
}
```

`ladder.deciding_level` is the first level that separated the candidates: `pre-screen`, `identity-tests`, or `footprint`. `regenerations` counts pre-screen failures redrawn for this action, and it may not exceed 2 — a third attempt is a character-bible or prompt problem, not a candidate.

If no human decision is possible at a human gate, stop before promoting generated candidates. Do not treat "go" as approval unless it clearly chooses a shown candidate id, and never read it as a grant of Full Automation. Deterministic cleanup of already-approved or existing source frames may continue without a new decision.

For the default directional workflow, record the `running-left` approval against the mirrored candidate, for example `running-left-from-right-flip`, with `source` pointing to that candidate's contact sheet and notes naming the approved `running-right` source candidate. Mirroring approved frames is deterministic, but it still needs its own decision record before `frames/running-left/` is written.

## Export Contract

The Geist app expects one atlas:

- Atlas size: `1536x1872`
- Columns: 8
- Rows: 9
- Cell size: `192x208`

Export may produce `spritesheet.png` and `spritesheet.webp`. Prefer lossless WebP for installed Geist Pets unless the app flow being tested explicitly needs PNG.
