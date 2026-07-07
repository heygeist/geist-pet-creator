# Geist Pet Source Contract

Use this contract for source bundles created by `geist-pet-creator`.

## Domain Language

- Use **Pet** for the animated Geist character.
- Use **Pet Metadata** for `pet.json`.
- Use **Pet bundle** or **Pet source bundle** for creation artifacts.
- Use **Pet Override** only when discussing app-specific Pet choices.
- Avoid using "custom pet" as canonical wording.

## Source Bundle Layout

```text
PetName.pet/
  pet.json
  character-bible.md
  sources/
    canonical-base.png
    candidates/
    references/
    raw/
  frames/
    <state>/<index>.png
  qa/
    approvals.json
    <sprite-action>-review.html
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

Maintain `qa/approvals.json` when generated art is used:

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
