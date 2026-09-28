#!/usr/bin/env python3
"""How big the Pet is, and where it sits. Decided once per bundle.

The generator and the auditor both answer these two questions, and until this
module existed they answered them separately, from whatever frame happened to be
in front of them. `CellTransform` fitted frame 0's alpha bounding box into the
cell, once per action run, which is nine different rulers for one Pet;
`refit_state` rescaled a bleeding row from that row's own union box. Neither
ever compared a state to the Pet.

Two defects came out of that, measured 2026-08-12 on shipped bundles:

  size     a state's body scaled to whatever its frame 0 happened to bound.
           On `FarWatcher` the widest frame 0 (`waving`, 129px) became the
           smallest state at 0.965x and the narrowest (`jumping`, 119px) the
           largest at 1.019x -- a 5.6% pop with nothing measuring it.
  position frames placed by a statistic that moves when a limb moves, so the
           body swam under its own animation. On `KarateCrownGuardian` still
           states drifted up to 6px with nothing correcting it.

A third one came out of the same blind spot and took a year longer to name,
because it hides INSIDE a state rather than between two:

  size      a body that ratchets frame to frame, because each frame is drawn
            with the previous one attached as a reference. On `FuseSprout` four
            states that should hold still spread 1.32x to 1.46x, and `failed`
            and `jumping` spread 1.50x and 1.21x while being entirely correct.
            `normalise_size` handles it, against `geist_house.SIZE_BUDGET`.

All three are fixed the same way, and it is the way every sprite engine already
does it: **one declared anchor for the whole character, and per-animation
permission to leave it.** Unity's `Sprite.pivot`, Unreal's pivot and SpriteKit's
`anchorPoint` are all authored constants; none is derived from artwork. The
industry's "centre" is the centre of a fixed declared rect. This pipeline read
it as the centre of this frame's alpha bbox, which is not a constant at all.

The anchor here is **bbox centre horizontally, base line vertically**, and both
halves were argued from measurement rather than taste:

  horizontal  the centroid was the obvious candidate and it is the worst of the
              three. It follows mass, so an arm moving drags it: measured 0.5px
              of bbox-centre travel against 9.9px of centroid travel across one
              `running` row, and 12.3px against 0.5px on a `waving` row in a
              second bundle. The silhouette's centre stays put while the mass
              inside it does not.
  vertical    these Pets float against a desktop and the eye locks to the
              bottom edge, which is where the visible hop lives -- `waving`
              resting 4.6px higher than every other state on `FarWatcher`.
              Bodies squash and stretch about their base, so pinning the base
              keeps the squash and removes the swim.

The base-line half is the weaker of the two claims and should be said plainly:
no engine documents bottom-centre as the right anchor for a character. Unity and
Unreal both ship it as an option and neither recommends it. It rests on this
repo's own measurements and on three hand-written normalizers in shipped bundles
that independently reached for it. Read
the repository's sanitized release evidence before changing it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from PIL import Image

from geist_grid import CELL_HEIGHT, CELL_WIDTH
from geist_house import motion_budget, size_budget
from geist_pixels import alpha_bbox, clear_transparent_rgb

# Lanczos softens an edge by about a pixel and a soft pixel still counts as
# visible, so anything fitting a body to a box reserves one.
RESAMPLE_BLEED = 1

# How far a state's size may sit from the bundle's ruler before the auditor
# spends a resample correcting it. Rescaling already-normalized art costs edge
# quality, so this is deliberately above the noise and below the 5.6% that was
# visible as a halo in a cross-state overlay.
SIZE_TOLERANCE = 0.03

# The same idea WITHIN a state, and deliberately three times tighter.
#
# These are not the same decision and the constant should not be shared. A state
# sitting 3% from the ruler is a static difference between two rows nobody plays
# side by side. A frame sitting 3% from its neighbours is a PULSE, played ten
# times a second, and the eye is far better at seeing change than at seeing size.
# Borrowing 0.03 here left a pinned state at 1.09x area spread where the
# deterministic pass the report measured reached 1.01-1.03x.
FRAME_SIZE_TOLERANCE = 0.01


@dataclass(frozen=True)
class Anchor:
    """Where one frame's body sits, and how much of it there is."""

    x: float  # bbox centre, horizontally
    base: int  # first row below the lowest visible pixel
    area: int  # visible pixels, not the bbox rectangle
    bbox: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


def measure(image: Image.Image) -> Anchor | None:
    """One frame's anchor, or None when nothing is visible."""
    bbox = alpha_bbox(image)
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    # Area is the visible pixel count, not the bbox rectangle. A raised arm adds
    # a few percent of area and fifteen percent of bbox height, so every
    # rectangle measure reimports the pose-dependence this module exists to
    # remove.
    area = image.getchannel("A").point(lambda value: 255 if value > 8 else 0).histogram()[255]
    return Anchor(x=(left + right) / 2, base=bottom, area=area, bbox=bbox)


def ruler(canonical_base: Image.Image, safe_padding: int, headroom: float = 0.0) -> Anchor:
    """The bundle's one declared target, in cell pixels.

    `sources/canonical-base.png` is already what every frame is counted against
    for identity, so it is what they are counted against for size and placement
    too. Deriving it here rather than caching it in a file means it cannot go
    stale against the art it describes.

    The base is stored at the provider's resolution, not at sprite scale, so it
    is fitted into the safe box exactly once. That single fit is the whole
    remaining use of fit-to-bounding-box in this pipeline, and it is sound where
    the per-state version was not: one decision, for one Pet, from the frame that
    defines the Pet -- rather than nine decisions from nine unrelated frame 0s.

    Two of the three coordinates fall out as constants and never touch the
    artwork: horizontally the cell centre, vertically wherever the fitted base
    lands. Only size is measured, because only size cannot be declared -- no
    image provider guarantees it draws at a consistent scale on its own canvas.
    """
    anchor = measure(canonical_base)
    if anchor is None:
        raise SystemExit(
            "sources/canonical-base.png has no visible pixels, so the bundle has no ruler. "
            "Every frame's size and placement is measured against it; approve a real base first."
        )
    room_x = CELL_WIDTH - 2 * safe_padding - 2 * RESAMPLE_BLEED
    room_y = CELL_HEIGHT - 2 * safe_padding - 2 * RESAMPLE_BLEED
    if headroom:
        room_x *= 1.0 - headroom
        room_y *= 1.0 - headroom
    scale = min(room_x / max(1, anchor.width), room_y / max(1, anchor.height))
    height = anchor.height * scale
    return Anchor(
        x=CELL_WIDTH / 2,
        base=round((CELL_HEIGHT + height) / 2),
        area=round(anchor.area * scale * scale),
        bbox=(
            round((CELL_WIDTH - anchor.width * scale) / 2),
            round((CELL_HEIGHT - height) / 2),
            round((CELL_WIDTH + anchor.width * scale) / 2),
            round((CELL_HEIGHT + height) / 2),
        ),
    )


def state_scale(anchors: list[Anchor], target: Anchor, safe_padding: int, headroom: float) -> float:
    """One scale factor for a whole state, from the bundle's ruler.

    The state's median frame is what gets matched to the ruler, not its frame 0.
    A median over four to eight frames averages the pose out; a single frame is
    the pose, which is how a `waving` frame 0 with its arm out shrank a whole
    state by 3.5%.

    Matching is by area, so `scale = sqrt(target area / median area)`. Known
    limit, stated rather than hidden: a state whose silhouette genuinely encloses
    more area -- arms spread wide -- is normalized towards the base and comes out
    marginally smaller than it was drawn. Every scalar read off a posed
    silhouette confuses pose with size to some degree; area confuses it least of
    the ones available, and a declared constant is not available because no image
    provider guarantees it draws at a consistent size on its own canvas.
    """
    median_area = statistics.median(anchor.area for anchor in anchors)
    if median_area <= 0:
        raise SystemExit("state has no visible pixels; cannot scale it against the ruler")
    scale = (target.area / median_area) ** 0.5

    # The ruler decides the size; the cell decides whether that size is allowed.
    # A state really is bigger than its base sometimes -- a jump stretches, a
    # prop swings out -- and the union of every frame is what has to clear the
    # safe box, not the median frame that set the scale.
    left = min(anchor.bbox[0] for anchor in anchors)
    top = min(anchor.bbox[1] for anchor in anchors)
    right = max(anchor.bbox[2] for anchor in anchors)
    bottom = max(anchor.bbox[3] for anchor in anchors)
    room_x = CELL_WIDTH - 2 * safe_padding - 2 * RESAMPLE_BLEED
    room_y = CELL_HEIGHT - 2 * safe_padding - 2 * RESAMPLE_BLEED
    if headroom:
        room_x *= 1.0 - headroom
        room_y *= 1.0 - headroom
    fits = min(room_x / max(1, right - left), room_y / max(1, bottom - top))
    return min(scale, fits)


def rest(anchors: list[Anchor], budget: tuple[int, int]) -> tuple[float, int]:
    """Where a state sits when it is not moving, per axis.

    The two axes need different answers because the motions are different
    shapes. A lateral glide oscillates about its middle, so the median is its
    rest. A jump only goes up, so its rest is its lowest frame -- taking the
    median there would leave the Pet hovering half-way through its own arc.
    """
    xs = [anchor.x for anchor in anchors]
    horizontal = statistics.median(xs)
    vertical = max(anchor.base for anchor in anchors) if budget[1] else statistics.median(
        anchor.base for anchor in anchors
    )
    return horizontal, int(vertical)


def placement(anchors: list[Anchor], target: Anchor, scale: float, budget: tuple[int, int]) -> tuple[int, int]:
    """The one offset that puts a scaled state's rest on the bundle's anchor."""
    rest_x, rest_base = rest(anchors, budget)
    return round(target.x - rest_x * scale), round(target.base - rest_base * scale)


def apply(image: Image.Image, scale: float, offset_x: int, offset_y: int) -> Image.Image:
    """Scale and place one frame into a cell."""
    scaled = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    cell.paste(scaled, (offset_x, offset_y))
    return clear_transparent_rgb(cell)


def _shift(image: Image.Image, dx: int, dy: int) -> Image.Image:
    if not dx and not dy:
        return image
    moved = Image.new("RGBA", image.size, (0, 0, 0, 0))
    moved.paste(image, (dx, dy))
    return moved


def register(
    cells: list[Image.Image], state: str, target: Anchor
) -> tuple[list[Image.Image], list[dict[str, object]]]:
    """Translate finished cells back onto the bundle's anchor, within budget.

    Whole pixels only. A sub-pixel correction would need a resample, and
    resampling a whole row to chase two pixels of drift costs more edge quality
    than the drift costs anyone watching.

    A pinned axis is corrected per frame, which removes the drift completely. A
    budgeted axis is corrected by one shared offset, which moves the state onto
    its anchor while leaving every frame's motion relative to its neighbours
    exactly as drawn -- and only clamps a frame that leaves the budget entirely.
    A state that overruns is pulled back rather than failed: this is free pixel
    arithmetic, and a hard error here would buy paid art for something a
    translation fixes.
    """
    budget_x, budget_y = motion_budget(state)
    anchors = [measure(cell) for cell in cells]
    live = [anchor for anchor in anchors if anchor is not None]
    if not live:
        return cells, []

    shared_x = shared_y = 0
    if budget_x:
        rest_x, _ = rest(live, (budget_x, budget_y))
        shared_x = round(target.x - rest_x)
    if budget_y:
        _, rest_base = rest(live, (budget_x, budget_y))
        shared_y = round(target.base - rest_base)

    out: list[Image.Image] = []
    notes: list[dict[str, object]] = []
    for index, (cell, anchor) in enumerate(zip(cells, anchors)):
        if anchor is None:
            out.append(cell)
            continue

        if budget_x:
            dx = shared_x
            drift = anchor.x + dx - target.x
            if abs(drift) > budget_x:
                dx -= round(drift - budget_x if drift > 0 else drift + budget_x)
        else:
            dx = round(target.x - anchor.x)

        if budget_y:
            dy = shared_y
            drift = anchor.base + dy - target.base
            if abs(drift) > budget_y:
                dy -= round(drift - budget_y if drift > 0 else drift + budget_y)
        else:
            dy = target.base - anchor.base

        out.append(_shift(cell, dx, dy))
        if dx or dy:
            notes.append({"frame": index, "dx": dx, "dy": dy})
    return out, notes


def _resize_about_anchor(image: Image.Image, factor: float, anchor: Anchor) -> Image.Image:
    """Rescale one finished cell and put its anchor back where it was.

    Resizing a cell resizes the empty margin with it, so a naive resize moves the
    body as well as sizing it. Both halves of the anchor are restored here --
    bbox centre horizontally, base line vertically -- which is the same anchor
    `register` uses, so the translation pass that follows finds the frame already
    close and does not have to undo a shift this pass introduced.
    """
    scaled = image.resize(
        (max(1, round(image.width * factor)), max(1, round(image.height * factor))),
        Image.LANCZOS,
    )
    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    cell.paste(scaled, (round(anchor.x - anchor.x * factor), round(anchor.base - anchor.base * factor)))
    return cell


def normalise_size(
    cells: list[Image.Image], state: str
) -> tuple[list[Image.Image], list[dict[str, object]]]:
    """Hold every frame of a state to the size its `SIZE_BUDGET` allows.

    `state_scale` already gives a state ONE shared scale against the bundle's
    ruler, deliberately, because for `failed` and `jumping` a size change between
    frames is the artwork. That is the right answer to "is this state the right
    size" and no answer at all to "does this state hold its size", which is a
    different defect with a different cause: one frame per call with the previous
    frame attached ratchets the body along the chain.

    So this runs per frame, against the state's own median rather than against
    the ruler, and what it is allowed to touch is declared rather than measured:

      pinned    every frame is scaled onto the state's median area.
      budgeted  frames are left as drawn, and only a frame outside the declared
                spread is pulled back to the edge of it -- the same treatment
                `register` gives a budgeted axis of travel, and for the same
                reason. A `failed` row that deflates to 1.5x is the pose; one
                that deflates to 4x is a defect, and only the second is touched.

    Area is the measure, matching `Anchor.area` and `state_scale`, because a
    bounding box grows when an arm goes up and this must not confuse a pose with
    a size. Scaling is about the anchor, so a frame changes size without moving.
    """
    anchors = [measure(cell) for cell in cells]
    live = [anchor for anchor in anchors if anchor is not None]
    if len(live) < 2:
        return cells, []

    median_area = statistics.median(anchor.area for anchor in live)
    if median_area <= 0:
        return cells, []

    # The budget is a spread -- largest over smallest -- so centred on the median
    # it allows sqrt(budget) of area either way, and the linear factor is the
    # square root of that again.
    allowed = size_budget(state) ** 0.5

    out: list[Image.Image] = []
    notes: list[dict[str, object]] = []
    for index, (cell, anchor) in enumerate(zip(cells, anchors)):
        if anchor is None:
            out.append(cell)
            continue

        ratio = anchor.area / median_area
        if allowed <= 1.0:
            target_ratio = 1.0  # pinned: every frame lands on the median
        elif ratio > allowed:
            target_ratio = allowed
        elif ratio < 1.0 / allowed:
            target_ratio = 1.0 / allowed
        else:
            out.append(cell)
            continue

        factor = (target_ratio / ratio) ** 0.5
        if abs(factor - 1.0) <= FRAME_SIZE_TOLERANCE:
            # Inside the noise. A resample costs edge quality, and below one
            # percent the correction is smaller than the antialiasing it would
            # disturb.
            out.append(cell)
            continue

        out.append(clear_transparent_rgb(_resize_about_anchor(cell, factor, anchor)))
        notes.append(
            {
                "frame": index,
                "was": round(ratio, 4),
                "now": round(target_ratio, 4),
                "factor": round(factor, 4),
            }
        )
    return out, notes


def size_spread(cells: list[Image.Image]) -> float:
    """Largest alpha area over smallest, in the unit `SIZE_BUDGET` is declared in."""
    areas = [anchor.area for anchor in (measure(cell) for cell in cells) if anchor is not None]
    areas = [area for area in areas if area > 0]
    if len(areas) < 2:
        return 1.0
    return max(areas) / min(areas)


def budget_for(state: str) -> tuple[int, int]:
    """The state's declared travel allowance, re-exported.

    Callers of this module should not have to know that the budget table lives
    with the rest of the house form; they ask the module that does the moving.
    """
    return motion_budget(state)


def size_budget_for(state: str) -> float:
    """The state's declared size allowance, re-exported alongside `budget_for`."""
    return size_budget(state)


def size_ratio(anchors: list[Anchor], target: Anchor) -> float:
    """A state's linear size against the ruler. 1.0 is the ruler exactly."""
    median_area = statistics.median(anchor.area for anchor in anchors)
    return (median_area / target.area) ** 0.5 if target.area else 1.0
