# Sprite registration, scale and drift — 2026-08-12

Research note for two open defects:

- **(a) cross-state scale pop** — the Pet is a different size in `idle` than in `jumping`, because
  `CellTransform.from_reference` (`scripts/generate_candidates.py`) fits *each action's own frame 0*
  alpha bounding box into the same 192x208 cell.
- **(b) within-state position jitter** — the Pet swims during playback, because that transform is
  anchored to frame 0's **bounding-box centre** and nothing re-registers the later frames.

Two kinds of evidence are used below and they are kept apart. **Cited** claims come from first-party
documentation, quoted with its URL. **Measured** claims come from running a survey over this repo's
own shipped bundles in `/Users/samithiwat/Desktop/work/geist/pet-design`, and are labelled as such.
Where the industry has no documented convention, § What This Could Not Source says so instead of
guessing.

---

## The one sentence

**No engine surveyed derives a sprite's anchor from the artwork. The anchor is authored data that
travels with the sprite, and every trimming feature in every atlas format exists precisely so that
the *measured* content bounds can never become the anchor.** The current pipeline does the one thing
the whole industry builds machinery to avoid: it measures the alpha and lets the measurement decide
where the character goes.

---

## 1. Registration, anchor, pivot — what the industry actually does

### 1.1 The anchor is declared, not measured

| Engine / tool | Where the anchor lives | Default | Source |
| --- | --- | --- | --- |
| Unity | `Sprite.pivot`, per sprite, authored in the importer | Center | [Sprite-pivot](https://docs.unity3d.com/ScriptReference/Sprite-pivot.html) |
| Unreal Paper2D | `UPaperSprite.pivot_mode` + `custom_pivot_point`, per sprite asset | `Center_Center` | [Sprite Editor Reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/sprite-editor-reference?application_version=4.27) |
| Godot | `Sprite2D`/`AnimatedSprite2D` `centered` + `offset`, per **node** | `centered = true`, `offset = (0,0)` | [class_sprite2d](https://docs.godotengine.org/en/stable/classes/class_sprite2d.html) |
| SpriteKit | `SKSpriteNode.anchorPoint`, unit coordinate space | `(0.5, 0.5)` | [anchorPoint](https://developer.apple.com/documentation/spritekit/skspritenode/anchorpoint) |

Unity is the most explicit that the pivot is measured against the **original**, untrimmed rectangle:

> "Location of the Sprite's pivot point in the Rect on the original Texture, specified in pixels."
> — [`Sprite.pivot`](https://docs.unity3d.com/ScriptReference/Sprite-pivot.html)

> "Sets the position of the point Unity uses for transformations such as rotation. Select Custom to
> set a custom pivot point."
> — [Sprite Editor window reference](https://docs.unity3d.com/Manual/sprite/sprite-editor/sprite-editor-window-reference.html)

Older Unity manuals said it more plainly, and the sentence is worth keeping because 6.5 dropped it:

> "Unity uses as the coordinate origin and main 'anchor point' of the graphic."
> — [Unity 2022.3 Sprite Editor](https://docs.unity3d.com/2022.3/Documentation/Manual/sprite-editor-use.html)

Unreal defaults its pivot to the centre of the **declared source region**, not to the artwork:

> Pivot Mode "Controls the way that the sprite pivot is calculated. It defaults to being computed as
> the center of the source region".
> — [Sprite Editor Reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/sprite-editor-reference?application_version=4.27)

`source_region` is itself authored — `source_uv` is "Position within SourceTexture (in pixels)" and
`source_dimension` is "Dimensions within SourceTexture (in pixels)"
([Paper2D Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/PaperSprite?application_version=5.1)).
Unreal also offers `snap_pivot_to_pixel_grid`, "Should the pivot be snapped to a pixel boundary?" —
a whole feature dedicated to keeping the anchor on integer pixels.

SpriteKit's anchor is likewise a fraction of the node's **declared size**, not of its visible pixels:

> "Defines the point in the sprite that corresponds to the node's position." … "You specify the value
> for this property in the unit coordinate space. The default value is `(0.5,0.5)`, which means that
> the sprite is centered on its position."
> — [`SKSpriteNode.anchorPoint`](https://developer.apple.com/documentation/spritekit/skspritenode/anchorpoint)

**Read the defaults carefully.** Every one of them is "centre" — but centre *of a fixed declared
rectangle*, which is a constant. That is not the same operation as "centre of this frame's alpha
bounding box", which is a variable recomputed per frame. The pipeline currently reads the industry
default as the second thing. It is the first.

### 1.2 Trimming must not move the sprite — the mechanism

Every atlas format that trims whitespace stores enough information to put the sprite back exactly
where it was. This is the direct primary-source answer to "why does bbox-centring jitter": the
formats treat the trimmed box as a *storage* optimisation and the original box as the *coordinate
space*.

**TexturePacker** states the rule most explicitly of any source found, by offering all three
behaviours as separate named settings
([Texture Settings](https://www.codeandweb.com/texturepacker/documentation/texture-settings)):

> **Trim** — "Removes the transparency around a sprite, but the sprite appears to have its original
> size when using it. **The anchor point used for sprite placement does not change.**"

> **Crop, keep position** — "…resulting in a smaller size when using it. The position in the original
> sprite is preserved, meaning its anchor point used for sprite placement remains unchanged."

> **Crop, flush position** — "…The position in the original sprite set to 0/0, i.e. sprite placement
> **changes** depending of the amount of removed transparent border."

That third option is the current pipeline's behaviour, named by the tool that treats it as the
non-default. TexturePacker carries the displacement as `spriteOffset`, "the offset of the sprite's
untrimmed center to the sprite's trimmed center", alongside `spriteSourceSize`, "size of the
untrimmed sprite"
([file formats](https://www.codeandweb.com/texturepacker/documentation/file-formats)); the custom
exporter exposes the same thing as `cornerOffset`, "offset from the top-left corner of the orignal
sprite to the top-left corner of the trimmed sprite" *(sic)*, plus `untrimmedSize`
([custom exporter](https://www.codeandweb.com/texturepacker/documentation/custom-exporter)). Its
pivot is a separate, authored thing: "The **pivot point** (or anchor point) specifies the position
inside the sprite that is used as a center for rotation and placement"
([UI overview](https://www.codeandweb.com/texturepacker/documentation/user-interface-overview)).

**Aseprite** carries the same pair in its sheet JSON — `spriteSourceSize` (the trimmed content's rect
*in the original canvas's coordinates*) and `sourceSize` (the full untrimmed canvas). Draw at
`dest + (spriteSourceSize.x, spriteSourceSize.y)` and a trimmed frame lands where it did before.
**Flagged**: Aseprite documents no prose semantics for these fields anywhere; the CLI page says only
that `--data` "Saves information about the exported sprite sheet in a JSON format"
([CLI](https://www.aseprite.org/docs/cli/)) and links to the author's example gists. The semantics
come from
[`doc_exporter.cpp`](https://github.com/aseprite/aseprite/blob/main/src/app/doc_exporter.cpp), where
`spriteSourceSize` is emitted from `sample.trimmedBounds()` and `sourceSize` from
`sample.originalSize()`.

Aseprite's slice pivot is likewise authored and optional: the Slice Properties dialog sets "a pivot
to specify the central/base location of the sprite inside the slice"
([slices](https://www.aseprite.org/docs/slices/)), stored per slice *key* as signed integer pixels
"relative to the slice origin" under flag bit 2
([ase-file-specs](https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md)), and
omitted from the JSON entirely when unset. Note the wording — Aseprite says *central/base*, treating
the two as interchangeable roles for the same field.

**libGDX** makes the round trip an API guarantee. `TextureAtlas.createSprite`: "If whitespace was
stripped from the region when it was packed, the sprite is automatically positioned as if whitespace
had not been stripped." `AtlasRegion.offsetX` is "The offset from the left of the original image to
the left of the packed image, after whitespace was removed for packing", and `originalWidth` is "The
width of the image, before whitespace was removed and rotation was applied for packing"
([TextureAtlas.java](https://github.com/libgdx/libgdx/blob/master/gdx/src/com/badlogic/gdx/graphics/g2d/TextureAtlas.java);
javadoc.io returned 403, so the identical javadoc comments were read from master). `AtlasSprite` sets
its origin to `region.originalWidth / 2f, region.originalHeight / 2f` — **the centre of the original
untrimmed image, never the centre of the trimmed content.**

**Three tools, three names, one invariant**: the anchor is expressed in untrimmed coordinates and the
trim offset is stored so it can be undone. Also note libGDX's `stripWhitespaceX`/`stripWhitespaceY`
both default to `false`
([texture packer wiki](https://libgdx.com/wiki/tools/texture-packer)) — trimming is opt-in, and the
wiki warns "Applications must take special care to draw these regions properly."

> ⚠️ **Naming collision, if any of this is ever borrowed as a field name.** TexturePacker's
> `spriteSourceSize` is a **size only (w,h)** of the untrimmed sprite, with displacement carried
> separately by `spriteOffset` as a **centre-to-centre** vector. Aseprite's `spriteSourceSize` is an
> **{x,y,w,h} rect** with a **top-left** origin. Same field name, different semantics, different
> reference point. And libGDX's `offsetY` is measured from the **bottom** of the original image,
> unlike Aseprite's and TexturePacker's top-based offsets.

**Unity.** Tight meshes crop pixels —

> "Tight mesh based on pixel alpha values. As many excess pixels are cropped as possible."
> — [`SpriteMeshType`](https://docs.unity3d.com/ScriptReference/SpriteMeshType.html)

— and the offset that undoes the crop is exposed:

> "Gets the offset of the rectangle this Sprite uses on its Texture to the original Sprite bounds. If
> Sprite mesh type is FullRect, offset is zero."
> — [`Sprite.textureRectOffset`](https://docs.unity3d.com/ScriptReference/Sprite-textureRectOffset.html)

**Godot.** `AtlasTexture.margin` is the un-trim, though the class reference is vague about it:

> "The margin around the region. Useful for small adjustments." … "If the `Rect2.size` of this
> property is set, the drawn texture is resized to fit within the margin."
> — [`AtlasTexture`](https://docs.godotengine.org/en/stable/classes/class_atlastexture.html)

That prose reads like scaling and is misleading. The engine source shows it is padding:
`get_width()` returns `rounded_region.size.width + margin.size.width`, and `draw()` offsets by
`margin.position`
([atlas_texture.cpp](https://raw.githubusercontent.com/godotengine/godot/master/scene/resources/atlas_texture.cpp)).
So `margin.position` = the trim offset and `margin.size` = `original_size - region_size` restores the
original box. **Flagged**: this is read from source, not stated in the docs.

**Godot's gap is instructive.** `SpriteFrames` — the resource behind `AnimatedSprite2D` — has **no
per-frame offset, pivot, or origin at all**; the only per-frame datum is `duration`
([class_spriteframes](https://docs.godotengine.org/en/stable/classes/class_spriteframes.html)).
`AnimatedSprite2D.offset` is a single node-level value shared by every frame of every animation. So
in Godot, per-frame alignment **must be baked into the frame images themselves**. That is exactly
the situation this pipeline is in: the Geist atlas is a uniform grid of 192x208 cells with no
sidecar pivot data, so registration has to be baked into the pixels at normalize time. There is no
later stage that can fix it.

### 1.3 Which anchor — centre, feet, centroid, or rig root

Sources genuinely differ here, and the difference is about what the anchor is *for*.

- **Bounding-box centre of a fixed rect** is the default everywhere (Unity `Center`, Unreal
  `Center_Center`, SpriteKit `(0.5,0.5)`, Godot `centered = true`). It is a default for convenience,
  not a recommendation for characters.
- **Bottom-centre** is a first-class named option in both Unity and Unreal —
  `SpriteAlignment.BottomCenter`, "Pivot is at the center of the bottom edge of the graphic
  rectangle" ([SpriteAlignment](https://docs.unity3d.com/ScriptReference/SpriteAlignment.html)); and
  `ESpritePivotMode::Bottom_Center`
  ([enum](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/Paper2D/ESpritePivotMode__Type)).
  Both engines ship it; **neither documents a recommendation to use it for characters.** The closest
  any first-party source comes to endorsing a base anchor is Aseprite's slice pivot, "a pivot to
  specify the central/**base** location of the sprite inside the slice"
  ([slices](https://www.aseprite.org/docs/slices/)) — which names base and centre as equal roles for
  the same field, but recommends neither. See § What This Could Not Source.
- **Centre of mass** appears in Unity's *root motion* machinery, not its sprite machinery: the Body
  Transform is "the mass center of the character", and the Root Transform is "a projection on the Y
  plane of the Body Transform" ([Root Motion](https://docs.unity3d.com/Manual/RootMotion.html)).
  Note the projection — even here the horizontal reference is mass, and the vertical reference is a
  ground plane, not the centroid.
- **Feet** is a documented *option* in Unity's humanoid import, as `Based Upon: Feet` for Root
  Transform Position (Y) ([AnimationClip](https://docs.unity3d.com/Manual/class-AnimationClip.html)).

**A centroid is not a bbox centre**, and scikit-image documents the first moment definition —
"The center coordinates (cr, cc) can be calculated from the raw moments as: `M[1, 0] / M[0, 0]`,
`M[0, 1] / M[0, 0]`"
([skimage.measure](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.regionprops)).
But scikit-image never contrasts the two, and there is no bbox-centre property; that contrast is
ours to draw, not theirs. It matters a lot here — see the measurement in § 5.2.

---

## 2. Scale consistency across states

The industry answer is **one shared ruler declared per project, applied to every sprite**, rather
than per-animation fitting. Unity states this as an imperative twice:

> "Select all your sprites in the Project window, and set their Pixels Per Unit properties to the
> same value."
> — [Add a pixel perfect camera](https://docs.unity3d.com/Manual/urp/2d-pixelperfect-prep-sprites.html)

> "After importing your textures into the project as Sprites, set all Sprites to the same Pixels Per
> Unit value." … Assets Pixels Per Unit: "Match this value to the Pixels Per Unit values of all
> Sprites"
> — [2D Pixel Perfect 5.0](https://docs.unity3d.com/Packages/com.unity.2d.pixel-perfect@5.0/manual/index.html)

PPU is the ruler itself: "The number of pixels in the Sprite that correspond to one unit in world
space" ([`Sprite.pixelsPerUnit`](https://docs.unity3d.com/ScriptReference/Sprite-pixelsPerUnit.html)).

**The shape of the convention is what transfers, not the number.** PPU makes scale a *declared
project constant* that every sprite is measured against. Nothing in it fits a sprite to its own
content. A Geist Pet has no world space and no camera, so PPU has no direct analogue — but "one
constant per character, applied to every frame of every state" is the same idea, and it is the
opposite of what `CellTransform.from_reference` does nine times per Pet.

**Caveat, stated honestly**: Unity's "same value" instruction appears only inside the Pixel Perfect
Camera setup pages. Unity does not state the general principle in the core Sprite or SpriteRenderer
manual pages, and no source found states a "character height in pixels" project constant. See
§ What This Could Not Source.

---

## 3. Registering independently generated frames to each other

Three techniques, with what each assumes. None is free.

### 3.1 Phase cross-correlation — translation only

`skimage.registration.phase_cross_correlation` returns a "Shift vector (in pixels) required to
register `moving_image` with `reference_image`", and `upsample_factor` means "Images will be
registered to within `1 / upsample_factor` of a pixel"
([API](https://scikit-image.org/docs/stable/api/skimage.registration.html#skimage.registration.phase_cross_correlation)).

The translation-only assumption is **not** stated on the API page. The explicit statement is in the
official gallery:

> "Phase correlation is an efficient method for determining translation offset between pairs of
> similar images." … "This approach relies on a near absence of rotation/scaling differences between
> the images, which are typical in real-world examples."
> — [plot_register_rotation](https://scikit-image.org/docs/stable/auto_examples/registration/plot_register_rotation.html)

Documented limits that bear on sprite frames:

- **Noise**: "the phase correlation method works well in registering images under different
  illumination, but is not very robust to noise"; "In a high noise scenario, the unnormalized method
  may be preferable."
- **Wraparound**: "The shift returned by this function is only accurate *modulo* the image shape, due
  to the periodic nature of the Fourier transform."
- **Masked mode loses subpixel and error**: `upsample_factor` is "Not used if any of
  `reference_mask` or `moving_mask` is not None", and the returned error "is not available and NaN is
  returned" for masked cross-correlation.

For alpha sprites the masked variant is the relevant one ("Boolean mask for `reference_image`. The
mask should evaluate to `True` (or 1) on valid pixels"), which means **the subpixel path and the
masked path are mutually exclusive**. That is a real constraint on any design that wants both.

### 3.2 ECC — richer motion model, needs a good start

`cv2.findTransformECC` "Finds the geometric transform (warp) between two images in terms of the ECC
criterion", supports `MOTION_TRANSLATION` / `MOTION_EUCLIDEAN` / `MOTION_AFFINE` (default) /
`MOTION_HOMOGRAPHY`, takes an optional `inputMask`, and returns "the final enhanced correlation
coefficient"
([video tracking group](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html#ga1aa357007eaec11e9ed03500ecbcbe47);
parameter bodies verified against
[tracking.hpp](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/video/include/opencv2/video/tracking.hpp)).

Its three documented assumptions are all awkward for AI-generated frames:

> "Unlike findHomography and estimateRigidTransform, the function findTransformECC implements an
> area-based alignment that builds on intensity similarities."

> "Note that if images undergo strong displacements/rotations, an initial transformation that roughly
> aligns the images is necessary."

> "Note that the function throws an exception if algorithm does not converges"

Intensity similarity is the problem: two frames of a Pet mid-squash are *not* photometrically the
same image warped, they are different drawings. ECC can also solve for scale (`MOTION_EUCLIDEAN`
upward), which is a double-edged tool here — it would silently absorb the very scale difference the
pipeline is trying to detect.

### 3.3 Centroid alignment

`scipy.ndimage.center_of_mass` "Calculate the center of mass of the values of an array at labels"
([docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.center_of_mass.html)) —
with an alpha channel as input this is an alpha-weighted centroid. It is cheap, has no motion model,
and needs no initial guess. Its assumption is that **mass distribution is stable**, which § 5.2 shows
is false for a Pet with a waving arm.

### 3.4 What the image providers actually promise

**Nothing about pixel registration.** Three first-party doc sets were checked and none mentions
sprites, animation frames, pixel alignment, or registration in any form. What they document is
*semantic* consistency — "the same character appears" — which is a categorically weaker property
than "the character's base line lands on the same row in frame N+1".

- Google: "Up to 4 images of characters to maintain character consistency"; the high-fidelity
  guidance is a prompting technique — "Ensure that the features of [element from image 1] remain
  completely unchanged."
  ([Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation))
- OpenAI documents the **opposite** of a guarantee: "While capable of producing consistent imagery,
  the model may occasionally struggle to maintain visual consistency for recurring characters or
  brand elements across multiple generations."
  ([image generation guide](https://developers.openai.com/api/docs/guides/image-generation))
- Black Forest Labs claims "FLUX excels at maintaining character consistency even after multiple
  sequential edits" with **no stated caveats at all**
  ([Kontext](https://docs.bfl.ai/kontext/kontext_image_editing)) — treat as the least rigorous of the
  three.

**Consequence for this pipeline**: frame-to-frame registration is not something a better prompt or a
better model buys. `geist_house.FRAMING` currently asks the model to "draw the character at the same
body size in every frame of this action, centred" — that is asking a provider for a guarantee no
provider offers. Registration has to be mechanical, downstream, in normalize.

---

## 4. Intended motion vs. drift

Every engine draws this line the same way in substance: **authored motion that moves the character is
separated from the pose, and the two are recombined by the controller.** The vocabulary is inverted
between engines, which is worth knowing before borrowing a word.

- **Unity** — "Root motion is the effect where an object's entire mesh moves away from its starting
  point but that motion is created by the animation itself"
  ([`Animator.applyRootMotion`](https://docs.unity3d.com/ScriptReference/Animator-applyRootMotion.html)).
  The mechanism for "this clip must not translate the character" is **Bake Into Pose**: "Bake
  vertical root motion into the movement of the bones. Disable to store as root motion." … "This
  means that this clip won't change the Game Object Height."
  ([AnimationClip](https://docs.unity3d.com/Manual/class-AnimationClip.html),
  [Root Motion](https://docs.unity3d.com/Manual/RootMotion.html)). Note that Unity splits it **per
  axis** — Root Transform Position (Y) and Position (XZ) are separate toggles.
- **Unreal** — "animations with a stationary Root Bone will play in place with no actual movement or
  displacement", versus root-bone data that "drives the character's movement"
  ([Root Motion](https://dev.epicgames.com/documentation/en-us/unreal-engine/root-motion-in-unreal-engine)).
- **Godot** — inverted: setting `AnimationMixer.root_motion_track` means "the transformation will be
  canceled visually, and the animation will appear to stay in place", and
  `get_root_motion_position()` hands you the delta "that can be used elsewhere"
  ([AnimationMixer](https://docs.godotengine.org/en/stable/classes/class_animationmixer.html)).
- **Spine** — "the character's position is driven by the animation according to the movement of the
  selected `Root Motion Bone`"
  ([spine-unity utility components](https://en.esotericsoftware.com/spine-unity-utility-components)).

So: Unreal's "in place" means the author never moved the root. Godot's root motion *makes* a moving
animation appear in place and returns the delta. Same split, opposite naming.

**The transferable rule**: the distinction is a **per-animation declaration**, not something inferred
from the pixels. No engine measures a clip to decide whether it was supposed to move. Unity's per-axis
Bake Into Pose is the closest fit to what a Geist state needs — `jumping` should be free on Y and
pinned on X; `running-right` is a lateral glide, so it may be free on X and pinned on Y.

---

## 5. What this repo already does — measured

### 5.1 Three hand-written normalizers independently chose the same anchor

Before `CellTransform` existed, three shipped bundles were normalized by hand-written scripts. All
three horizontally centre on the bbox and all three **bottom-align vertically**:

| Bundle | Script | Placement |
| --- | --- | --- |
| `DoraemonGeist.pet` | `sources/raw/normalize_candidate.py:143` | `((CELL[0] - sprite.width) // 2, CELL[1] - 14 - sprite.height)` |
| `MangoStickyRiceSpirit.pet` | `qa/normalize_row.py:43-44` | `x = (CELL_W - resized.width) // 2` ; `y = 198 - resized.height` |
| `GreekPhoenix.pet` | `qa/normalize_selected_candidate.py:137-138` | `x = (192 - sprite.width) // 2` ; `y = 200 - sprite.height` |

Not one of them centres vertically on the bbox. **`CellTransform`, which centres on the bbox in both
axes, is a regression from what the hand path did.**

`normalize_candidate.py` also had the intended-motion carve-out already, in prose:

> "Use one scale across an action while retaining only meaningful motion. Grid rows in generated
> sheets often have different placement despite showing the same animation sequence. Ordinary actions
> are therefore re-based to a shared baseline; jumping retains its source position so the apex
> remains visibly higher."

That is § 4's per-animation declaration, implemented by hand, as a `preserve_position` flag. And
`GreekPhoenix.pet/qa/motion_audit.py` carries the same carve-out on the audit side:
`if max(areas)/max(1,min(areas)) > 1.35 and state != "jumping"`.

`references/qa-rubric.md` already speaks this language too — it rejects "Large baseline jumps **not
required by the state**" and says "`jumping` may move vertically but must not scale-drift."

### 5.2 The measurement

Survey over `frames/` in 7 shipped bundles, 192x208 cells, alpha threshold 8. Per state: bbox height
range, and the span (max − min) of the top edge, bottom edge, bbox centre-y and centroid-y.

**Defect (a), cross-state scale pop, is real and large.** Frame-0 bbox height across a Pet's states:

| Bundle | spread | min → max |
| --- | --- | --- |
| `CuteLazyCriminal.pet` | **41.5%** | 130 → 184 |
| `DoraemonGeist.pet` | **20.0%** | 150 (`jumping`) → 180 (`running`) |
| `GreekPhoenix.pet` | 16.5% | 158 (`running-left`) → 184 (`idle`) |
| `VegetaGeist.pet` | 15.1% | 139 (`jumping`) → 160 (`running`) |
| `FarWatcher.pet` | 8.1% | 172 → 186 |
| `KarateCrownGuardian.pet` | 2.2% | 181 → 185 |
| `MangoStickyRiceSpirit.pet` | 0.0% | 184 → 184 |

**Defect (b) — and why the bbox centre is the wrong thing to hold.** Within a single state the bbox
centre moves a great deal while the base line does not move at all:

| Bundle / state | bbox height | top edge span | **bottom edge span** | bbox centre-y span | centroid-y span |
| --- | --- | --- | --- | --- | --- |
| `CuteLazyCriminal` `running-left` | 123–181 | 58 | **0** | 29.0 | 24.3 |
| `MangoStickyRice` `running-left` | 152–184 | 32 | **0** | 16.0 | 11.9 |
| `DoraemonGeist` `running-left` | 131–158 | 27 | **0** | 13.5 | 17.9 |
| `VegetaGeist` `running` | 130–160 | 30 | **0** | 15.0 | 19.7 |

This is squash-and-stretch about a fixed base. The body's height changes by up to 47%, the base does
not move by a single pixel, and the **bbox centre moves 29 px purely as an artifact of the squash**.
Anything that holds the bbox centre steady will fight the squash and re-introduce exactly the
vertical swim it was meant to remove.

Two more results from the same survey:

- **The centroid is not a safe anchor either.** `DoraemonGeist` `waving`: bbox centre-x span 0.5 px,
  **centroid-x span 12.3 px**. The arm moves, the mass follows it, the silhouette does not. Centroid
  alignment would drag the whole body sideways to compensate for a wave.
- **The base line already discriminates intended motion.** Bottom-edge span is 0 in the median for
  every state — except `jumping`, median 10 px, max 30 px. `DoraemonGeist` `jumping` bottoms run
  194, 194, 179, 164, 194: a rise and a return, i.e. a preserved arc. The one state whose base is
  allowed to move is the one state that is supposed to move.

**Honest caveat on these numbers**: the bottoms are pinned because those three normalizers pinned
them (§ 5.1), and the bundles predate `CellTransform`. The measurement demonstrates that base-line
registration *is achievable and does preserve the intended motion*; it is **not** independent
evidence that the model naturally draws a stable base. Frames straight from a provider have not been
measured here. That is the gap a follow-up should close.

---

## 6. What this means for the two defects

### Vocabulary warning

`references/contract.md` already defines **anchor frame** as "the frame a state's other frames are
measured against". Do not reuse "anchor" for a registration point. Suggested terms, matching the
sources: **pivot** or **registration point** for the point, **base line** for the horizontal line it
sits on, and **ruler** for the shared per-character scale.

### For (a), cross-state scale

The convention is one declared constant per character, applied everywhere (§ 2). Concretely: derive
the scale **once per Pet** — the natural place is `sources/canonical-base.png`, which is already the
identity lock every state is generated against — record it in the bundle, and have all nine actions
read it. `CellTransform.from_reference` should stop being called nine times per Pet with nine
different reference frames.

Note that this makes `--motion-headroom` a property of the Pet rather than of an action, and it makes
`CellTransform.growth_allowance` a one-time check at canonical-base review — which is what its own
docstring already says it is for ("the one moment when swapping it is free is the canonical-base
review").

`refit_state` in `audit_spritesheet.py` is a partial version of the right idea already: it derives
one factor from the **union** bbox of a state and applies it to every frame, "so relative motion
survives exactly". Its scope is the bug — a per-state rescue means each state can still land at a
different size. Under a per-Pet ruler, a bleeding state is a signal that the *ruler* is wrong, not
that one state needs its own factor.

### For (b), within-state position

Stop centring on the bbox. The measurement in § 5.2 is unambiguous: the bbox centre is the least
stable feature of the four measured, and it is unstable *because of the animation working
correctly*. The base line was stable to 0 px in every non-jumping state, and the centroid moved 12 px
on a wave.

Concretely: register **horizontally on the bbox centre** and **vertically on the bottom edge**,
pinned to a constant row per Pet. This is `SpriteAlignment.BottomCenter` (§ 1.3), and it is what the
hand path converged on three times.

The horizontal half is the weaker half, and worth saying so. Horizontal bbox-centre span was ≤1.5 px
in most measured states, but not all: `VegetaGeist` `waiting` spans 17 px and `DoraemonGeist`
`jumping` spans 20 px on X. Some of that is intended (a jump with lateral travel), some is drift, and
this survey cannot separate the two. The vertical half is the one the measurement actually settles.

**The house form makes this an unusually clean fit.** `geist_house.LEGLESS_BODY` says the Pet "floats
clear of any ground and its body ends in a smooth rounded base", with no floor plane and no cast
shadow. So there are no feet to place and no contact point to preserve — the base of the silhouette
*is* the body's own bottom edge, and nothing in the artwork competes with it for the role. The usual
objection to bottom-alignment (a foot lifting off the ground drags the whole sprite down) cannot
arise for a character with no feet.

Registration must be baked into the pixels, because the Geist atlas is a bare uniform grid — `pet.json`
carries only `id`, `displayName`, `description`, `spritesheetPath`, with nowhere to put a pivot, and
Godot's `SpriteFrames` (§ 1.2) shows what that costs: there is no downstream stage that can correct
it.

### For the jumping carve-out

Make it a **per-action declaration**, following § 4 and the `preserve_position` flag that already
existed. Per-axis, as Unity does it: `jumping` free on Y and pinned on X; the lateral states pinned
on Y. Do not try to infer it from the pixels — no engine does, `motion_audit.py` did not, and
`qa-rubric.md` already words the rule as "not required by the state".

### On the registration algorithms

For this problem the § 3 algorithms look like the wrong tool, and that is worth saying plainly so a
future agent does not reach for them by default. Phase correlation assumes near-absence of scaling
differences (§ 3.1) — but frames that legitimately squash *do* differ in scale, so it would try to
"fix" the animation. ECC needs intensity similarity and can absorb scale into the warp (§ 3.2). Both
are estimators recovering an unknown transform; base-line registration is not an estimation problem
at all, because the target row is a number the pipeline chooses. Reach for phase correlation only if
a measured-on-raw-provider-frames follow-up shows the base line itself is unreliable.

---

## 7. What this could not source

Stated as gaps rather than guesses.

1. **"Put the pivot at the feet/base for characters."** No first-party source found. Unity and Unreal
   both *ship* `BottomCenter` / `Bottom_Center` as named presets, but neither documents a
   recommendation to use it for characters. Every "pivot at the feet" phrasing found was Unity
   Discussions or forum content — user posts, not documentation. Unity's own e-book *2D game art,
   animation, and lighting for artists* is genuinely first-party but is form-gated behind an
   HTTP 403, so it could not be read. **The bottom-centre recommendation in § 6 rests on this repo's
   own measurement and its three hand normalizers, not on an industry citation.**
2. **"Character height in pixels" as a project constant.** No source found in any of the surveyed
   docs. Unity's shared-PPU imperative is the closest analogue and appears only in the Pixel Perfect
   Camera setup pages, never as a general principle in the core Sprite manual.
3. **An explicit guarantee that trimming does not move a sprite** — from *Unity*. Unity documents the
   *mechanism* (`textureRectOffset`, pivot in "the Rect on the original Texture") but never states
   the invariant as a sentence; Full Rect, where "offset is zero", is its bulletproof route.
   TexturePacker and libGDX **do** state it outright (§ 1.2), so the claim itself is well sourced —
   just not from Unity.
4. **Aseprite's sheet-JSON field semantics.** No prose specification exists in aseprite.org's docs;
   `--data` is documented only as "Saves information about the exported sprite sheet in a JSON
   format", with the author's example gists as the nearest thing to a spec. `spriteSourceSize`,
   `sourceSize`, `trimmed` and `rotated` were established from `doc_exporter.cpp`. Likewise, no
   official Aseprite statement says `--trim` preserves position — that is read from source. Two
   incidental hazards found in that source, if the format is ever consumed: `rotated` is a hardcoded
   `false`, and `--ignore-empty` **drops** frames from the JSON list entirely rather than emitting
   the 1x1 placeholder that otherwise preserves frame ordering.
5. **libGDX's `.atlas` text grammar and TexturePacker's trim/pivot pages.** Neither exists as
   documentation. libGDX's wiki says only that the packer emits "a text file that describes all the
   images packed on the pages"; the field grammar is in the parser and writer. TexturePacker has no
   dedicated trimming or pivot page — the quotes in § 1.2 come from Texture Settings, File Formats,
   Custom Exporter and the UI overview. `javadoc.io` returned HTTP 403, so libGDX javadoc was read
   from master source instead (identical text).
6. **Godot's `AtlasTexture.margin` un-trim semantics** are confirmed from engine source, not from the
   class reference — whose prose ("resized to fit within the margin") reads as scaling and is
   misleading.
7. **No first-party Godot guidance on frame alignment or trimming** exists on the official 2D sprite
   animation tutorial. This is a confirmed absence, not a failed search: Godot's model assumes a
   uniform grid where alignment is implicit in the cell geometry.
8. **`phase_cross_correlation`'s translation-only assumption** is not stated on the API page; it is
   stated on the `plot_register_rotation` gallery page. Cite that page, not the API page.
9. **OpenCV never calls ECC "gradient-based."** The docs establish only that it is iterative with
   termination criteria. That characterisation belongs to the Evangelidis & Psarakis paper.
10. **scikit-image does not contrast "centroid" with "bounding-box centre."** Both exist
    independently; bbox centre is not a property at all. The contrast in § 1.3 and § 5.2 is drawn
    here, from this repo's measurement, not quoted.
11. **No image provider documents any frame-to-frame or pixel-registration property** (§ 3.4). Not a
    weak claim found — an absence across Google, OpenAI and BFL.
12. **Drift on raw provider frames is unmeasured.** Every number in § 5.2 comes from frames already
    normalized by the hand scripts. The survey should be repeated on `sources/candidates/` raw output
    before the base-line assumption is trusted for frames the pipeline has not yet touched.
13. **How the Geist runtime positions a cell** is unknown — no first-party Geist source was available
    here. `pet.json` carries no pivot field, so the working assumption is that the 192x208 cell is
    drawn as-is and registration must be baked into the pixels. Unverified.

---

## Reproducing the measurement

Run as `python3 survey.py <bundle>.pet ...` from `~/Desktop/work/geist/pet-design`. Not committed —
it is short enough to paste, and a checked-in copy would drift from the audit it is meant to
cross-check.

```python
import sys, os, glob
from PIL import Image

def stats(path):                       # alpha bbox + alpha-weighted centroid
    m = Image.open(path).convert("RGBA").getchannel("A").point(lambda v: 255 if v > 8 else 0)
    bb = m.getbbox()
    if not bb: return None
    l, t, r, b = bb; px = m.load(); sx = sy = n = 0
    for y in range(t, b):
        for x in range(l, r):
            if px[x, y]: sx += x; sy += y; n += 1
    return dict(t=t, b=b, h=b - t, cy=(t + b) / 2, gy=sy / n, cx=(l + r) / 2, gx=sx / n)

def span(v): return max(v) - min(v)

for bundle in sys.argv[1:]:
    print("===", os.path.basename(bundle))
    print("%-14s %2s %5s %5s %6s %6s %6s %6s" %
          ("state", "n", "hmin", "hmax", "top_sp", "bot_sp", "cy_sp", "gy_sp"))
    f0 = {}
    for state in sorted(os.listdir(os.path.join(bundle, "frames"))):
        d = os.path.join(bundle, "frames", state)
        if not os.path.isdir(d) or state in ("failed", "review"): continue
        rows = [s for s in (stats(p) for p in sorted(glob.glob(d + "/*.png"))) if s]
        if len(rows) < 2: continue
        f0[state] = rows[0]["h"]
        print("%-14s %2d %5d %5d %6.1f %6.1f %6.1f %6.1f" % (
            state, len(rows), min(r["h"] for r in rows), max(r["h"] for r in rows),
            span([r["t"] for r in rows]), span([r["b"] for r in rows]),
            span([r["cy"] for r in rows]), span([r["gy"] for r in rows])))
    if f0:
        hi, lo = max(f0.values()), min(f0.values())
        print(">> frame-0 height spread across states: %.1f%% (%d..%d)\n" % ((hi / lo - 1) * 100, lo, hi))
```

`bot_sp` is the base line's movement and `cy_sp` is the bounding-box centre's. The gap between those
two columns is the whole argument in § 5.2. The numbers quoted there are what this produced on
2026-08-12.
