#!/usr/bin/env python3
"""The house form, and the geometry of a concept sheet.

Three scripts need this and none of them owns it. `generate_candidates.py` draws
sheets and `crop_gallery_cells.py` cuts cells out of them. Maintainer release tests
measure them. If each carried its own copy of the house form text or its own
idea of where cell 4 is, they would drift, and the drift would be invisible
until a crop came back with half a mascot in it.

Cell indices are 1-based and row-major, because the identity-lock paragraphs in
the prompt are numbered the same way. Paragraph 4 describes `cell-04`. Keeping
one numbering removes the translation layer where an off-by-one would hide.
"""

from __future__ import annotations

from pathlib import Path

# The house form, stated compactly enough to sit inside a prompt. The long form
# with the hex values is the table in references/identity-blend.md; this is what
# an image generator is actually given.
HOUSE_FORM = (
    "One compact rounded legless floating body with a single thick sky-blue outline of even "
    "weight, a cream body area, two small ink dot eyes, one tiny simple mouth, exactly one "
    "centred orange heart physically inside the silhouette, tiny attached rounded arm nubs, "
    "flat colour fills with very few interior lines, props thick and short and rounded and "
    "physically attached, no legs, no feet, no knees, no shoes, no floor plane, no cast "
    "shadow, no detached effect, and the whole character readable at 192x208."
)

# What never crosses from a source into a Pet, whatever the source does with it.
NEVER_TRANSFERS = (
    "legs, feet, knees, shoes, realistic hands, fingers, noses, realistic faces, muscular "
    "build, real weapons, blades and edges, blood, franchise titles, official logos, exact "
    "emblems, kanji, readable letters or numbers, watermarks, aura, energy effects, speed "
    "lines, impact marks, scenery, floor planes, cast shadows, detached props, floating "
    "accessories, extra characters, gradients, screentone, painterly texture, glossy 3D, "
    "and black exterior outlines"
)

# Prompt blocks every frame call carries. They live here, beside the house form,
# because they are facts about the house form -- and a rule that exists only in
# SKILL.md prose is a rule the model never sees. That gap is what let a
# directional state draw legs across all eight of its frames on 2026-08-12, and
# lose the whole run.
#
# Each block states the target and puts the ban last, because a prohibition
# drags the forbidden thing into context and half-reads as an instruction: "no
# legs" spends most of its weight on `legs`. The ban is the guardrail; the
# target ahead of it is the steering.

# The first sentence asks for something no provider offers. OpenAI documents the
# opposite -- that a model "may occasionally struggle to maintain visual
# consistency" -- and no image provider documents any frame-to-frame or
# pixel-registration property at all. It stays because it costs nothing and may
# help at the margin, but the guarantee lives in `geist_registration`, which
# measures the frames that came back rather than trusting the ask. Asking was
# what produced the 5.6% size pop measured on FarWatcher.
FRAMING = (
    "Framing: draw the character at the same body size in every frame of this action, "
    "centred, with the whole body and every prop well inside the canvas and an even clear "
    "margin of at least 15% of the canvas on all four sides. When a pose would carry any "
    "part towards an edge, make the motion smaller and leave the character where it is."
)

LEGLESS_BODY = (
    "Body: the Pet floats clear of any ground and its body ends in a smooth rounded base. Below "
    "that base there is nothing but the Pet's own hanging parts: draw no legs, feet, knees, shoes "
    "or foot-step poses."
)

# For the four states whose NAME pulls hardest towards legs. It ends with
# LEGLESS_BODY rather than restating it, so a prompt carries one or the other
# and the ban has one wording wherever it lands.
# "Trailing shapes off the back of the body" was measured drawing detached speed
# lines -- 2-4 blue streaks floating beside the Pet on every frame of
# running-right and jumping, on a build where idle and waving came back clean.
# The phrase means a trailing shape OF the body; the model read it as a trailing
# mark BESIDE it. Detached marks are on the never-carry list, and the anatomy
# audit counts them as stray fragments, which is one of only two things that
# buys paid art. So the phrase now says whose shapes they are, and the ban is
# stated here rather than left to SKILL.md, which the model never reads.
LEGLESS_MOTION = (
    "Movement: carry the motion with a lean, a drift, a glide, a sideways translation of the "
    "whole body, soft squash and stretch, and trailing shapes that are part of the body itself "
    "and joined to it. Draw no speed lines, motion trails, streaks, dashes, swooshes, wind "
    "marks, dust, sparks or any other mark floating beside or behind the character: every mark "
    "in the frame is part of the Pet and touches it. "
) + LEGLESS_BODY

FLAT_FIELD = (
    "Keep the whole area behind the character one flat uniform field, edge to edge: no panel, "
    "box, card, border, frame, vignette or backdrop, and no ground plane, floor line, horizon "
    "or cast shadow."
)

# Every frame prompt carries this, because a state that only bobs its body reads
# as the same Pet wearing different labels. The signature is what makes `waiting`
# unmistakably THIS Pet waiting: its face landmarks, crown cue, prop and palette
# accents all take part in the motion. A frame where only the body's vertical
# position changed is a pre-screen reject, not a restrained variant.
SIGNATURE_MOTION = (
    "Expression: animate the face and the character's signature parts in every frame, not "
    "just the body's position. The eyes, mouth, arm nubs, crown cue, prop and palette "
    "accents each move in a way that fits this state and fits this Pet's personality: "
    "eyes narrow, widen, glance or blink; the mouth opens, flattens or curves; arm nubs "
    "lift, droop or gesture; the crown cue and prop sway, perk or wilt with the motion. "
    "At least the face and one other body part must visibly change across the frames of "
    "this action. A state carried by body translation alone is unfinished art."
)

# Every multi-frame state loops in the app, so the last frame must flow back into
# the first. A cycle whose ends disagree pops once per loop, forever.
SMOOTH_LOOP = (
    "Loop: this action plays as a seamless repeating cycle, so keep the motion smooth "
    "and continuous across frames and make the last frame flow naturally back into the "
    "first with no snap, pop or pose jump at the wrap point."
)

# The `failed` state reads sad, deflated and negative in EVERY frame -- that is
# the whole meaning of the state in the app. A single cheerful, neutral or
# celebratory frame in the row breaks the read, so the ban is total rather than
# a matter of degree.
FAILED_MOOD = (
    "Mood: this is the `failed` action, so every frame shows a sad, disappointed, "
    "deflated or discouraged Pet and nothing else. Drooping arm nubs, downturned or "
    "flat mouth, sad or downcast eyes, a slightly sagged or deflated body. Draw no "
    "smile, grin, smirk, cheerful eyes, thumbs-up, wave, bounce, sparkle, celebration "
    "or any other happy, neutral or positive read in any frame."
)

# The states whose NAME pulls hardest towards legs. The word in the prompt is
# what does the damage, so these are the ones that carry LEGLESS_MOTION.
MOTION_STATES = frozenset({"running-right", "running-left", "running", "jumping"})

# How far a state's body may travel from where the bundle says it rests, per
# axis, in cell pixels: (horizontal, vertical). Anything past this is drift, and
# `geist_registration` translates it back.
#
# Declared, never inferred. Every engine that solves this solves it the same way
# -- Unity's per-axis Bake Into Pose, and the equivalents in Unreal, Godot and
# Spine -- because no measurement can tell a jump arc from a body that wandered.
# Measured 2026-08-12 on two shipped Pets: a `waiting` row drifting 5.5px with
# nothing declaring that it may, and `jumping` arcs of 9px and 22px that must
# survive. Both numbers come out of the same pixels, so only a declaration
# separates them.
#
# A zero pins the axis: every frame lands on the bundle's anchor. That is not a
# claim the Pet is rigid -- the body still squashes and stretches around a
# pinned base, which is how sprite animation has always worked. A state that
# wants a hover declares the hover here.
STILL = (0, 0)
MOTION_BUDGET: dict[str, tuple[int, int]] = {
    "idle": STILL,
    "waving": STILL,
    "waiting": STILL,
    "review": STILL,
    "failed": STILL,
    "running-right": (14, 0),  # lateral glide; measured span 9px
    "running-left": (14, 0),
    "running": (14, 0),
    "jumping": (0, 26),  # the arc; measured 22px on KarateCrownGuardian
}


def motion_budget(state: str) -> tuple[int, int]:
    """The travel allowance for a state, defaulting to pinned.

    An unknown state pins rather than floats: a new state that nobody has
    thought about should hold still and be visibly wrong, not wander and look
    like art.
    """
    return MOTION_BUDGET.get(state, STILL)


# How much a state's body may change SIZE across its own frames, as the ratio
# between its largest and smallest alpha area. `MOTION_BUDGET` says where a body
# may go; this says how big it may get once it is there. The two are the same
# argument made about different pixels, and until this table existed only half
# of it was declared.
#
# The gap was expensive. `generate_candidates.py` draws one frame per call with
# the previous frame attached as a reference, so size ratchets along the chain
# and frames 00-01 come back smallest every time. Measured 2026-08-13 on
# FuseSprout, as drawn:
#
#     review   1.46x    idle   1.41x    waiting 1.37x    running 1.32x
#     failed   1.50x    jumping 1.21x
#
# The first four are defects and the last two are the artwork -- a `failed` Pet
# deflates and a `jumping` one squashes and stretches. Both sets come out of the
# same pixels, exactly as with travel, so only a declaration separates them.
# Three paid redraws went into telling the model to hold its size and bought
# nothing: a SIZE LOCK in `--extra-prompt` took `idle` from 1.41x to 1.14x once,
# then the next state came back at 0.54x. It is noise, not control. Scaling each
# frame to the state's median area is deterministic, free, and landed all five
# pinned states at 1.01-1.03x in one pass.
#
# PINNED normalises every frame of the state onto the state's median. A budgeted
# state keeps its drawn sizes and is only pulled back when it overruns, which is
# how `register` already treats a budgeted axis of travel.
PINNED = 1.0
SIZE_BUDGET: dict[str, float] = {
    "idle": PINNED,
    "waving": PINNED,
    "waiting": PINNED,
    "review": PINNED,
    "running-right": PINNED,
    "running-left": PINNED,
    "running": PINNED,
    "failed": 1.6,  # deflation is the pose; measured 1.50x
    "jumping": 1.35,  # squash and stretch is the pose; measured 1.21x
}


def size_budget(state: str) -> float:
    """The size allowance for a state, defaulting to pinned.

    Same default and same reasoning as `motion_budget`: a new state nobody has
    thought about should hold its size and be visibly wrong, rather than breathe
    and look like art.
    """
    return SIZE_BUDGET.get(state, PINNED)

# Cell count -> (columns, rows, aspect ratio).
#
# The aspect ratio is not decoration. A 5x2 grid requested on a square canvas
# letterboxes every cell, and the mascots shrink to fit the wasted height, which
# is the one thing a concept sheet cannot afford: a cell too small to name is not
# an option, it is a smudge.
# Only three aspect ratios are actually served, so the grid is chosen to suit the
# ratio rather than the other way round. Every layout here lands its cells at or
# near square, which is what keeps a mascot readable.
#
# Counts that do not tile one of those ratios take the next grid up and leave
# cells empty. That costs a little canvas and risks the model drawing into the
# gap, which pre-screening catches; a long thin cell is not recoverable at all.
GRID_LAYOUTS: dict[int, tuple[int, int, str]] = {
    3: (2, 2, "1:1"),  # 4 rects, 3 filled -- 3x1 needs a ratio nothing serves
    4: (2, 2, "1:1"),
    5: (3, 2, "3:2"),  # 6 rects, 5 filled
    6: (3, 2, "3:2"),
    8: (3, 3, "1:1"),  # 9 rects, 8 filled -- 4x2 wants 2:1, which is rejected
    9: (3, 3, "1:1"),
    10: (4, 3, "4:3"),  # 12 rects, 10 filled -- 5x2 wants 5:2, also rejected
    12: (4, 3, "4:3"),
}

# Aspect ratios that actually draw. Measured 2026-08-12 by probing models
# directly, one ratio at a time.
#
# This is NOT the provider's schema enum, and the difference is the whole point.
# The schema accepts 1:2, 2:1, 4:1, 8:1, 9:16, 16:9 and more -- and then *no
# provider serves them*, so the request dies anyway with a second, different 400:
#
#     schema reject:   "ZodError ... invalid_value"          (e.g. 3:1, 5:2)
#     provider reject: "No provider for <model> supports
#                       the requested parameters"            (e.g. 2:1, 4:1)
#
# Validating against the schema enum passes the first check and fails the second,
# which is how "8 cells at 4x2 @ 2:1" sat in this table looking correct. Only
# near-square ratios are served. Verified good on both openai/gpt-image-2 and
# google/gemini-3.1-flash-lite-image; verified bad: 2:1 and 4:1 on both.
#
# Add to this set only after probing the ratio against a real model. Reasoning
# from the schema is what produced two rounds of this bug.
PROVIDER_ASPECT_RATIOS = frozenset({"1:1", "3:2", "4:3"})

MAX_SHEET_CELLS = 12
MIN_PASSING_CELLS = 3

HOUSE_STYLE_NAMES = ("geist-house-style.jpg", "geist-house-style.jpeg", "geist-house-style.png")


def check_aspect_ratio(aspect_ratio: str) -> None:
    """Refuse an illegal ratio here, on a free local read.

    The alternative is discovering it at the provider, mid-run, as an HTTP 400
    that names no cause -- which is exactly how the 3:1 entry survived into a
    shipped grid table and then killed a whole eval case.
    """
    if aspect_ratio in PROVIDER_ASPECT_RATIOS:
        return
    legal = ", ".join(sorted(PROVIDER_ASPECT_RATIOS))
    raise SystemExit(
        f"aspect ratio '{aspect_ratio}' is not one the provider accepts, so this request "
        f"would fail with HTTP 400 before any model saw it.\n\nAccepted: {legal}"
    )


def layout_for(cells: int) -> tuple[int, int, str]:
    """The grid and aspect ratio for a cell count, or a refusal that says why."""
    if cells in GRID_LAYOUTS:
        columns, rows, aspect_ratio = GRID_LAYOUTS[cells]
        check_aspect_ratio(aspect_ratio)
        return columns, rows, aspect_ratio
    if cells > MAX_SHEET_CELLS:
        raise SystemExit(
            f"{cells} cells is over the {MAX_SHEET_CELLS}-cell cap. Split the brainstorm "
            f"across two sheets: past twelve, a cell stops being large enough to name, and "
            f"an unnameable cell is not an option the human can choose between."
        )
    supported = ", ".join(str(count) for count in sorted(GRID_LAYOUTS))
    raise SystemExit(f"no grid layout for {cells} cells; supported counts are {supported}")


def cell_id(index: int) -> str:
    """1-based, row-major, zero-padded: `cell-04`."""
    return f"cell-{index:02d}"


def cell_rects(width: int, height: int, columns: int, rows: int) -> list[tuple[int, int, int, int]]:
    """Row-major (left, upper, right, lower) rects covering the sheet.

    Boundaries are computed from the full width and height each time rather than
    accumulated from a cell size, so rounding cannot leave a seam of unclaimed
    pixels down the right edge or along the bottom.
    """
    rects: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        upper = round(height * row / rows)
        lower = round(height * (row + 1) / rows)
        for column in range(columns):
            left = round(width * column / columns)
            right = round(width * (column + 1) / columns)
            rects.append((left, upper, right, lower))
    return rects


def _occupied_runs(flags: list[bool], minimum: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return [run for run in runs if run[1] - run[0] >= minimum]


def detect_bands(mask, columns: int, rows: int) -> tuple[list[tuple[int, int]] | None, list[tuple[int, int]] | None]:
    """Where the mascots were actually drawn, as row and column bands.

    An even grid is what the sheet was ASKED for, not necessarily what came
    back. Measured 2026-08-12: `openai/gpt-image-2` drew a 4x3 sheet whose first
    row ran to 245 of a 675-pixel canvas while even thirds put the boundary at
    225, so cutting on even thirds sliced 20 pixels off the bottom of every
    mascot in that row. The clip is small, silent, and lands on the outline.

    Returns (row_bands, column_bands), or None for either axis when the number
    of bands found does not match the grid -- touching mascots merge into one
    band, and a guess there would be worse than the even grid.
    """
    width, height = mask.size
    pixels = mask.load()
    step = 3  # sampling every third line is plenty and keeps this cheap

    row_flags = [any(pixels[x, y] for x in range(0, width, step)) for y in range(height)]
    column_flags = [any(pixels[x, y] for y in range(0, height, step)) for x in range(width)]

    row_bands = _occupied_runs(row_flags, max(2, height // 50))
    column_bands = _occupied_runs(column_flags, max(2, width // 50))
    return (
        row_bands if len(row_bands) == rows else None,
        column_bands if len(column_bands) == columns else None,
    )


def bands_to_rects(
    width: int,
    height: int,
    row_bands: list[tuple[int, int]],
    column_bands: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Row-major rects cut at the midpoints of the gutters between bands.

    Cutting at the midpoint rather than at a band edge keeps a margin of paper
    around each mascot, so a cell stays a usable reference image instead of a
    tight crop that may already have shaved the outline.
    """

    def edges(bands: list[tuple[int, int]], limit: int) -> list[int]:
        cuts = [0]
        for before, after in zip(bands, bands[1:]):
            cuts.append((before[1] + after[0]) // 2)
        cuts.append(limit)
        return cuts

    xs = edges(column_bands, width)
    ys = edges(row_bands, height)
    return [
        (xs[column], ys[row], xs[column + 1], ys[row + 1])
        for row in range(len(row_bands))
        for column in range(len(column_bands))
    ]


def house_style_path(bundle: Path | None = None) -> Path:
    """Image 2 on every derived call, and a sheet's only lock before a base exists.

    The bundle's own copy wins, so a packet stays reproducible after the skill
    moves or updates. The shipped asset is the fallback, not the default.
    """
    directories: list[Path] = []
    if bundle is not None:
        directories.append(bundle / "sources" / "references")
    directories.append(Path(__file__).resolve().parent.parent / "assets")

    for directory in directories:
        for name in HOUSE_STYLE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate

    raise SystemExit(
        "no house-style reference found. Copy $SKILL_DIR/assets/geist-house-style.jpg into "
        "the bundle as sources/references/geist-house-style.jpg -- a bundle without it has "
        "no house-form lock, so nothing stops the source's art style from winning."
    )
