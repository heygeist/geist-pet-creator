#!/usr/bin/env python3
"""The house form, and the geometry of a concept sheet.

Three scripts need this and none of them owns it. `generate_candidates.py` draws
sheets, `crop_gallery_cells.py` cuts cells out of them, and `eval_providers.py`
measures them. If each carried its own copy of the house form text or its own
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

# Cell count -> (columns, rows, aspect ratio).
#
# The aspect ratio is not decoration. A 5x2 grid requested on a square canvas
# letterboxes every cell, and the mascots shrink to fit the wasted height, which
# is the one thing a concept sheet cannot afford: a cell too small to name is not
# an option, it is a smudge.
# Every ratio here must come from PROVIDER_ASPECT_RATIOS, so some grids get the
# nearest legal ratio rather than the one they would like. 3x1 wants 3:1 and 5x2
# wants 5:2; both are rejected, and both take 2:1 instead. Their cells then run
# portrait rather than square, which suits a mascot -- a Pet is taller than it is
# wide anyway.
GRID_LAYOUTS: dict[int, tuple[int, int, str]] = {
    3: (3, 1, "2:1"),  # wants 3:1, which the provider rejects
    4: (2, 2, "1:1"),
    5: (3, 2, "3:2"),  # six rects, five filled; the last one stays empty
    6: (3, 2, "3:2"),
    8: (4, 2, "2:1"),
    9: (3, 3, "1:1"),
    10: (5, 2, "2:1"),  # wants 5:2, which the provider rejects
    12: (4, 3, "4:3"),
}

# The aspect ratios the provider will accept. This is a closed enum, not a
# free-form ratio: a value outside it is rejected with HTTP 400 before the model
# is ever reached.
#
# Measured 2026-08-12, the expensive way. A whole eval case died on all seven
# contenders at once because the table above asked for "3:1". Seven identical
# 400s read like a provider outage, not like a typo in this file.
PROVIDER_ASPECT_RATIOS = frozenset({
    "1:1", "1:2", "1:4", "1:8", "2:1", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "9:19.5", "19.5:9",
})

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
