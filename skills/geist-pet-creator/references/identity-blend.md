# Identity Blend

Read this before creating a **derived Pet** — a Pet built from something that already exists and is already recognizable: a character from a series, a mascot, a brand figure, a game or film archetype, a real object or animal with a known look.

A derived Pet is not a small copy of its source, and it is not a plain Geist wearing a hat. It is a blend: the source's identity cues transplanted onto the Geist house form. Both halves have to survive, and they conflict constantly, so the resolution order below is the whole discipline.

## Two Locks

A derived Pet carries two locks instead of one.

- **House form** — the Geist visual language every Pet shares. Fixed, and identical across every Pet ever made.
- **Identity cues** — the handful of features that make this particular source recognizable. Different for every Pet.

`sources/canonical-base.png` is where the two meet. It is still the single identity lock for the animation states, so a blend that is wrong there is wrong in all 57 frames.

## Resolution Order

When a cue and the house form disagree, resolve in this order:

1. **House form invariants never yield.** A cue that cannot be drawn inside them gets translated, or dropped.
2. **Identity cues yield only to the house form.** They outrank every style detail.
3. **Style detail yields freely.** Line count, shading, and interior decoration are the first things to simplify.

Two sentences carry it:

> If a style simplification would erase a recognizable feature, keep the feature and simplify how it is drawn.
> If a recognizable feature would break a house-form invariant, keep the invariant and translate the feature.

Skipping the second sentence is how a concept sheet drifts back into looking like official franchise art with a heart pasted on.

## House Form

These are the invariants. They hold for every Pet, derived or original.

| Invariant | Rule |
| --- | --- |
| Body | one compact rounded floating spirit form; no legs, no feet, no knees, no shoes |
| Outline | a single thick smooth rounded Sky exterior outline (`#2FB8EC`), even weight all the way round |
| Body area | Cream / warm-white (`#FFF4E2`) dominant face and body area |
| Eyes | two small solid Ink dots (`#20201C`), unless a signature eye *is* one of the cues |
| Mouth | one tiny simple mouth; the expression varies, the geometry stays small |
| Heart | exactly one Mango heart (`#FF7A33`), centered, physically inside the silhouette |
| Arms | tiny rounded attached nubs; no wrists, no fingers |
| Fill | flat color panels, very few interior lines, no gradient, gloss, texture, screentone, or 3D |
| Props | thick, short, rounded, toy-like, and physically attached to the body |
| Scale | the whole character reads at `192x208` |
| Ground | no floor plane, no cast shadow, no detached effect, no floating accessory |

The table is the rule; the image is what actually communicates it to an image generator. The skill ships one:

```bash
"$SKILL_DIR/assets/geist-house-style.jpg"
```

Attach it to every derived generation call. Copy it into each derived bundle as `sources/references/geist-house-style.jpg` too, so the bundle stays reproducible after the skill moves or updates. A bundle with no house-style reference has no house-form lock, so establish it before generating anything.

Twelve original Geist Pets fill that image, with no source character among them. Study what they share and what they vary: the body outline changes shape freely — comet, sprout, flame, terminal, lantern, capsule, crystal, buoy — while the face language, the outline weight, and the heart never move. That is the budget a derived Pet works inside.

## Cue Budget

Pick **4 to 6 identity cues** and rank them. More than six turns the sprite into a costume study that stops reading at thumbnail scale; fewer than four produces an interchangeable blob.

Cues by strength, strongest first:

- **Crown cue** — the hair or headwear silhouette. This is what a viewer reads first at `192x208`, so it is where identity is won or lost. Give it real silhouette area: spikes, a bob with squared ends, a straw brim, a drill puff.
- **Color block** — one or two flat costume panels in the source's signature colors. Blocks, not garment detail.
- **Prop** — **exactly one**, thick and rounded and attached. A second prop costs more than it returns.
- **Face landmark** — at most two: glasses, whiskers, a scar mark, a cheek mark, a signature eye color.
- **Expression** — eye angle plus mouth shape, carrying the personality. Free, in the sense that it costs no silhouette area.
- **Species tab** — ear tabs, antennae, a body tint, a tail curl, when the source is not human-shaped.

Two rules apply to the whole budget:

- The silhouette does the naming. A cue that only survives at full resolution is not a cue.
- Countable cues become rows in the **Part Manifest**, so the anatomy audit can count them. "Exactly three sword shapes" and "one lightning-bolt tail" are manifest rows, not prose.

## Using references responsibly

The skill ships only `assets/geist-house-style.jpg`, an original house-form
reference described in [asset-guide.md](asset-guide.md). Identity references
must be supplied by the user and must be original, licensed, or otherwise
authorized for the requested use. Keep provenance in the candidate packet. Do
not copy third-party reference images into the skill or repository.

## Identity Blend Section

`character-bible.md` for a derived Pet carries an `## Identity Blend` section, above the Part Manifest. It records what the blend decided, so a later repair does not quietly re-decide it.

```markdown
## Identity Blend

Source: original storm courier — alert, silver-crested, carries one message capsule.

| Rank | Source cue | Geist translation | Reads at 192x208 |
| --- | --- | --- | --- |
| 1 | forked silver storm crest | two broad rounded silver crest forks on the dome | yes, silhouette |
| 2 | indigo courier hood | one flat indigo crown panel with attached side tabs | yes, silhouette |
| 3 | brass message capsule | one thick rounded capsule attached at the side | yes, prop |
| 4 | pale lightning sash | one flat pale-yellow diagonal body panel | yes, color block |
| 5 | alert expression | raised dot eyes and a tiny determined mouth | yes, expression |

Dropped: boots and legs — house form. Loose paper — detached props. Chest badge — competes with the Mango heart for the same area.
```

The `Dropped` line is not optional. A cue that was considered and rejected tends to come back during repair unless the rejection is written down.

## Two Reference Images

Every derived generation call attaches at least two images, and the prompt names both:

- **Image 1 — identity reference.** The source character, the identity moodboard, the approved sheet cell being rendered at sprite scale, or the approved canonical base. Which one depends on the phase; see the table below.
- **Image 2 — house-style reference.** `sources/references/geist-house-style.<ext>`.

State which one wins on conflict, in the prompt itself. Store both under `sources/references/` and list them in the packet's `inputs.json`, so the candidate is reproducible.

Image 1 changes as the bundle progresses. Image 2 never does. The three sets:

| Phase | Image 1 | Image 2 | Also attached |
| --- | --- | --- | --- |
| `concept-sheet` | the identity reference, for a derived sheet only — an original cast sends no Image 1 | house-style reference | nothing; no canonical base exists yet |
| `canonical-base` | the cropped sheet cell when a sheet ran, otherwise the identity reference | house-style reference | nothing |
| animation states | `sources/canonical-base.png` | house-style reference | the previous frame of the same action |

Keep the roles in that order across a bundle; swapping them between calls changes which lock dominates and the drift is hard to trace afterwards.

## Prompt Skeleton

Derived-Pet prompts read best in this field order. Every field earns its place; the identity locks carry the specificity.

```text
Use case: stylized-concept | style-transfer
Asset type: <what this image is for>
Input images: Image 1 is <identity reference>. Image 2 is <house-style reference>. Do not edit either image.
Primary request: <one paragraph — what to make, and the instruction to translate into compact rounded
  non-human Geist companions rather than miniature figures of the source>
Shared Geist identity: <the house form, stated compactly>
Identity locks: <one numbered paragraph per cell, in exact row-major order, each naming crown cue,
  color blocks, the single prop, face landmarks, expression, and the centered Mango heart>
Scene/backdrop: plain warm off-white paper; invisible <C>-column by <R>-row grid; generous negative
  space; no dividers
Style/medium: <house form as rendering instructions> — no gradients, texture, shadows, gloss,
  screentone, painterly marks, or 3D
Composition/framing: exactly one centered full-body mascot per cell, equal visual scale and weight,
  ample padding, nothing cropped, no overlap, front or soft three-quarter view, no text
Constraints: <what must stay attached, toy-like, countable, and sprite-viable>
Avoid: <the never-transfers list, plus this source's specific traps>
```

Write identity locks as physical description, never as a name. "Broad woven straw hat with a red band, messy black hair crest, tiny stitch scar below the left eye" produces the character; the character's name produces the source's art style along with it.

## Never Transfers

None of these cross from the source into a Pet, whatever the source does with them:

- Human anatomy: legs, feet, knees, shoes, realistic hands, fingers, noses, realistic faces, muscular build
- Real weapons, blades and edges, blood, gore, threatening combat poses
- Franchise titles, official logos, exact emblems, kanji, readable letters, numbers, watermarks
- Action effects: aura, energy, lightning as an effect, speed lines, impact marks, battle damage
- Scenery, floor planes, cast shadows, detached props, floating accessories, extra characters
- Gradients, screentone, painterly texture, glossy 3D, black exterior outlines

The deliverable is an original Geist mascot that evokes something, not a reproduction of it. Prefer a descriptive mascot name for `pet.json` `id` and `displayName` — `silver-lightning-cub`, `Saiyan Hero` — over the source character's name.

## Concept Sheet Route

When the human brainstorms rather than naming one finished Pet, draw a sheet first and let them pick from it. Two shapes trigger it: **many characters** — a cast, a crew, a roster, a franchise — or **many design directions for one Pet**. The full route, including the grid table and the per-cell failure policy, is in [generation-workflow.md](generation-workflow.md) § Concept Sheet Route. What follows is what the route asks of a *blend*.

1. Create a staging bundle `<Thing>Concepts.pet` when the sheet spawns many Pets; write straight into `<Name>.pet` when it spawns one.
2. Draw **one sheet image**, not one image per character: an invisible grid on warm off-white paper, one complete centered mascot per cell, equal scale and baseline, no dividers, no text. Six characters go 3x2, ten go 5x2, twelve go 4x3.
3. Write one numbered identity-lock paragraph per cell, in the exact row-major order the grid will be read in. The paragraph number *is* the cell id: paragraph 4 describes `cell-04`.
4. Pre-screen cell by cell and record a verdict per cell, then render `qa/concept-sheet-review.html` and ask the human to choose by cell id.
5. Crop each chosen cell with `crop_gallery_cells.py` and carry it into its Pet bundle as `sources/references/selected-<cue>.png`.

**Every cell spends its own cue budget.** Four to six ranked cues per cell, one prop per cell, a crown cue that does the naming. A sheet is not a place to economise on identity locks — a vague paragraph produces the generic blob, and it produces it six times at once.

**The house form is the one thing cells share.** Cells may differ in silhouette, crown cue, prop, and palette accents; they may not differ in the invariants from the House Form table above. A sheet whose cells disagree about outline weight or the heart has drifted toward source copy across the whole grid.

A sheet cell is a concept, not a canonical base. It still goes through the `canonical-base` gate as its own candidate, generated at sprite scale with the crop as Image 1, before anything is written to `sources/canonical-base.png`.

**V2 refinement.** When a sheet reads generic, run a second round that keeps the same row-major families and the same layout, and *strengthens identity* rather than adding decoration. Rewrite the weak identity locks to be more specific and more physical. Adding a prop or an accessory to a cell that failed the naming test almost never fixes it; a stronger crown cue usually does.

## Failure Modes

Every derived Pet fails in one of two directions, and the fixes are opposites.

### Franchise copy — the source style won

Symptoms: the source's own outline color instead of Sky; original body proportions kept whole; a full figure with legs; the face drawn in the source's rendering style; the Mango heart missing, tacked on, or floating outside the silhouette.

Fix: re-prompt from the house form outward, transplanting cues onto the Geist body. The fix is a change of direction, not of degree — simplifying the source's art step by step arrives back here.

### Generic blob — the house form won

Symptoms: the character cannot be named from a thumbnail; the cues collapsed into one hat and one color; several sheet cells are interchangeable; identity carried only by detail visible at full resolution.

Fix: strengthen the crown cue and the silhouette. Do not add props — a second prop makes the sprite busier without making it more nameable.

### Three tests

- **Naming test** — show a 192px thumbnail to someone who knows the source. They should name it in about two seconds.
- **Silhouette test** — fill the sprite solid black. The crown cue and prop shape should still say who it is.
- **Heart test** — remove the Mango heart and the Sky outline. If what remains looks like official art from the source, the blend failed toward franchise copy.

Run all three before the candidate reaches a human. They are cheap, and they catch the two failure modes at the only point where fixing them is still cheap.
