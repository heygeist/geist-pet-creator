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
    <sprite-action>-review.html
    final-audit.json
    final-audit.html
    repair-log.json
  final/
```

`frames/` is the durable source of truth. `sources/raw/` may contain high-resolution generations, strips, masks, or rejected attempts, but those files are not exported directly.

`sources/candidates/` contains generated art before approval. Candidate files are review artifacts, not source frames. A candidate becomes source truth only after agent pre-screening and human approval of that exact candidate id, then normalization into `sources/canonical-base.png` or `frames/`.

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
| 1 | three-point moss-green hair | three broad rounded moss crest spikes on the dome | yes, silhouette |
| 2 | tied dark-green bandana | one thick dark-green band across the crown, ends attached | yes, silhouette |
| 3 | three katana | exactly three broad rounded toy sword shapes attached behind the body | yes, silhouette |
| 4 | dark-green haramaki | one flat dark-green waist panel | yes, color block |
| 5 | stern half-lidded stare | narrowed dot eyes and a short flat mouth | yes, expression |

Dropped: boots and legs — house form. Visible blades and edges — no realistic weapons. Chest scar — competes with the Mango heart.
```

Rank 1 is the cue that does most of the naming, normally the crown cue. Keep the table to 4-6 rows and to a single prop. The `Dropped` line is required, including its reasons.

Every countable cue also gets a Part Manifest row, so the anatomy audit counts it like any other part.

A derived Pet with no `## Identity Blend` section fails candidate pre-screen; it is not a warning-level gap, because the two locks cannot be checked against each other without it. Original Pets do not need the section.

A derived bundle also carries `sources/references/geist-house-style.jpg`, copied from `assets/geist-house-style.jpg` in the skill. The bundle holds its own copy so a packet stays reproducible after the skill moves or updates, and `inputs.json` must list it alongside the identity reference for every derived generation call.

Read [identity-blend.md](identity-blend.md) before filling it in, and [../assets/README.md](../assets/README.md) for the reference galleries.

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

Maintain `qa/approvals.json` when generated art is used. The required approvals are the ten sprite actions plus `final-audit`.

The `final-audit` approval carries an `atlas_digest`, so an approval cannot outlive the artwork it approved. Change one pixel of one frame and the digest changes, which reopens the gate:

```json
{
  "candidate_id": "final-audit-22db90a8d97f",
  "approved_action": "final-audit",
  "approved_for": "final/spritesheet.webp",
  "atlas_digest": "22db90a8d97fbf6e42e31823a1e7edac602461e6c9b80bfcb63293343558f508",
  "source": "qa/final-audit.html",
  "decision": "approved",
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
    "approver_note": "Chosen from waiting-a, waiting-b, and waiting-c.",
    "decided_at": "2026-07-05T00:10:00Z"
  }
]
```

If no human approval is possible in the current run, stop before promoting generated candidates. Do not treat "go" as approval unless it clearly chooses a shown candidate id. Deterministic cleanup of already-approved or existing source frames may continue without a new approval.

For the default directional workflow, record the `running-left` approval against the mirrored candidate, for example `running-left-from-right-flip`, with `source` pointing to that candidate's contact sheet and notes naming the approved `running-right` source candidate. Mirroring approved frames is deterministic, but it still requires human approval before `frames/running-left/` is written.

## Export Contract

The Geist app expects one atlas:

- Atlas size: `1536x1872`
- Columns: 8
- Rows: 9
- Cell size: `192x208`

Export may produce `spritesheet.png` and `spritesheet.webp`. Prefer lossless WebP for installed Geist Pets unless the app flow being tested explicitly needs PNG.
