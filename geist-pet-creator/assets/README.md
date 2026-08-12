# Reference Assets

Reference images the skill attaches to generation calls, and reads from when judging a candidate. Read [../references/identity-blend.md](../references/identity-blend.md) for the rules these images illustrate.

Attach them by absolute path from the skill directory:

```bash
SKILL_DIR=/absolute/path/to/geist-pet-creator
"$SKILL_DIR/assets/geist-house-style.jpg"
```

Copy `geist-house-style.jpg` into a new derived bundle as `sources/references/geist-house-style.jpg`, so the bundle stays reproducible after the skill moves or updates.

## geist-house-style.jpg

**The house form lock. Attach this to every derived generation call as Image 2.**

Twelve original Geist Pets, no source character in any of them. This is what the house form looks like with nothing borrowed: one compact rounded legless floating body, a single thick Sky outline, a Cream body area, two Ink dot eyes, one tiny mouth, exactly one centered Mango heart, tiny attached arm nubs, flat fills, no floor and no cast shadow.

Note what the twelve share and what they vary. The body outline changes shape freely — comet, sprout, flame, terminal, lantern, cloud, capsule, snowman, crystal, moon, toolbox, buoy — while the face language, the outline weight, and the heart never move. That is the budget a derived Pet works inside.

This file is byte-identical to the reference the existing `pet-design` bundles already carry, so a bundle that adopts it does not change its own lock.

## identity-cues-ranked.jpg

**Cue ranking, and how much identity a crown cue carries.**

Twelve derived Pets, one source each. Every cell names its source almost entirely through the crown cue plus one prop:

| Cell | Crown cue | Prop | Other cues |
| --- | --- | --- | --- |
| 1 | five jagged green hair spikes | fishing rod | green jacket panels with red piping |
| 2 | white starburst hair | — | lightning-bolt tail, lavender collar |
| 3 | blonde bob, squared ends | one chain loop | scarlet eyes, blue tabard |
| 4 | black side-part crest | briefcase | round glasses, navy suit, red tie |
| 8 | mint insect crown with a fin | — | antennae, tail curl, emerald plates |
| 10 | two golden drill puffs | — | magenta bows, pink scalloped dress |

Cells 2, 8, and 10 carry no prop at all. The crown cue alone does the naming. Compare cell 6, whose black cloak and book are correct but whose crown cue is a plain hair cap — it is the weakest read in the sheet.

Every body underneath is still the house form. Cover the top third of any cell and the twelve become near-identical.

## identity-cues-crew.jpg

**The one-prop budget, and cues on non-human bodies.**

Ten derived Pets. Each carries exactly one prop, and each prop is thick, short, rounded, toy-like, and physically touching the body: a slingshot, a staff, a book, a cane, three sword shapes.

The three-sword cell is the countable-cue case. "Exactly three broad rounded sword shapes, one vertical and two diagonal" is a Part Manifest row, so the anatomy audit can catch a fourth sword or a missing one. Write cues this way whenever they can be counted.

Four cells replace the Cream body with a species tab instead of adding decoration: a brown reindeer face, a blue shark body, a skull face, a cyborg lower body. A source that is not human-shaped spends its budget on body form, not on costume.

## identity-cues-labeled.jpg

**Gallery labeling, and the strongest and weakest reads side by side.**

Six derived Pets in a 3x2 grid with Sky A-F labels — the labeling convention for a concept gallery. Cells stay on warm paper, at equal scale and baseline, one complete Pet each, no other text.

A and B are pure crown-cue reads: two black hair silhouettes and nothing else would do it. C, E, and F show body-tint cues — green, spotted green, pink — where the source is not human-colored. D is the sparse case worth studying: a pearl body, a violet crown plate, side plates, and one attached tail curl, and it still names its source.

Also note what none of the six do. No aura, no energy, no action pose, no muscular build, no readable letters on the belts or patches. Those all belong to the sources and none of them crossed over.

## identity-cues-franchise-copy.jpg

**A counter-example. Do not use this as a style target.**

Twelve derived Pets where the source style won, which is the **franchise copy** failure mode. The prompt behind it ranked identity above everything, so the house form had nothing to defend itself with.

Read the specific breakages:

- Legs and feet on every cell. The house form has neither.
- Original franchise body proportions kept whole, rather than translated onto the rounded floating body.
- Faces drawn in the source's rendering style — its noses, its eye shapes, its cheek blush.
- The Mango heart reduced to a small badge on a pocket or a shirt, rather than the centered anchor of the silhouette.

Apply the heart test to any cell: remove the Mango heart and the Sky outline, and what is left is the source's own artwork. That is the whole failure in one check.

The fix is direction, not degree. Re-prompt from the house form outward and transplant cues onto the Geist body. Simplifying the source's art step by step arrives back here.

## Provenance

All five images come from `pet-design` bundles. The galleries are downscaled to 1536px wide and saved as JPEG q88; `geist-house-style.jpg` is copied byte for byte.

| Asset | Source |
| --- | --- |
| `geist-house-style.jpg` | `OnePieceGeistConcepts.pet/sources/references/IMG_7114.JPG` |
| `identity-cues-ranked.jpg` | `HunterXHunterGeistConcepts.pet/sources/raw/hunter-x-hunter-concept-gallery-v2-master.png` |
| `identity-cues-crew.jpg` | `OnePieceGeistConcepts.pet/sources/raw/straw-hat-crew-gallery-master.png` |
| `identity-cues-labeled.jpg` | `DragonBallConcepts.pet/sources/candidates/z-character-gallery-v1/candidate.png` |
| `identity-cues-franchise-copy.jpg` | `DoraemonCastConcepts.pet/sources/raw/doraemon-cast-geist-v2-master.png` |
