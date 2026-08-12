#!/usr/bin/env python3
"""Measure image models on the job this skill actually gives them.

Not on generic prompt following. A Pet is 57 frames of one creature, and 56 of
them are drawn with an approved identity lock attached as a reference image, so
a model that draws beautifully from a bare prompt and drifts the moment you show
it a character is useless here. Every case below therefore sends a reference.

Case kinds:

  identity hold  An approved Pet's own art goes in as the reference. The model
                 redraws that exact creature in a new pose. Scored on whether
                 the cues survive the pose change.
  creativity     No character reference at all -- only the house-style sheet,
                 plus a physical description of a source the model must render
                 as a new Pet. Never the source's name: a name drags the whole
                 franchise art style in with it, which is the failure mode
                 references/identity-blend.md calls "franchise copy".
  concept sheet  One call returning many mascots on a grid. A single mascot is
                 scored on whether its identity survived; a sheet is scored on
                 whether its cells are COMPARABLE, because that is the only
                 reason to draw them together instead of separately. Six new
                 faults become possible in a grid and none of them exist for one
                 mascot: wrong cell count, cells at different sizes, cells at
                 different baselines, a mascot crossing into its neighbour,
                 drawn dividers or text, and -- worst -- concepts placed in the
                 wrong cells.

Wrong-order is the dangerous one, because nothing downstream can detect it. The
human clicks `cell-04` meaning the fourth identity lock they wrote, and if the
model put that concept somewhere else they have chosen a Pet they did not want.
The `order-` case exists to make that fault mechanically visible.

Two fallbacks, because most models need one:

  parameter      Some models answer HTTP 400 for output_format/background
                 rather than ignoring them. The request goes again without them.
  chroma-key     Some models accept those fields and return opaque pixels
                 anyway. The request goes again asking for a flat green
                 background, and the green is keyed out here.

Of seven contenders only two return true alpha unaided, so the chroma path is
the normal path, not an edge case. Measured 2026-08-12.

Scoring is two-stage. This script auto-scores the mechanical criteria from
references/qa-rubric.md and renders the silhouette test from
references/identity-blend.md. A human does the naming test and the blend
verdict, in the review page it writes. Identity stays human by design.

The key comes from OPENROUTER_API_KEY and never enters this file or its output.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from geist_house import HOUSE_FORM, cell_id, cell_rects, layout_for
from geist_pixels import alpha_bbox, data_uri
from generate_candidates import (
    CHROMA_SUFFIX,
    ProviderConfig,
    alpha_is_real,
    api_key,
    build_sheet_prompt,
    call_provider,
    decode_image,
    endpoint,
    key_out_chroma,
    opaque,
    set_base_url,
)

# --------------------------------------------------------------------------- #
# Contenders
# --------------------------------------------------------------------------- #

# Every id here was confirmed by a live request. GET /api/v1/models lists
# neither openai/gpt-image-2 nor x-ai/grok-imagine-image-2.0, and both answer
# requests, so that endpoint is a hint and never proof a model is missing.
#
# The qwen models were measured and then removed. Alibaba's filter rejected the
# Doraemon reference with "Input data is suspected of being involved in IP
# infringement" -- a provider that refuses your own approved reference art
# cannot serve a skill built around derived Pets, at any price.
CONTENDERS = (
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "openai/gpt-image-2",
    "x-ai/grok-imagine-image-2.0",
)

FULL_PET_FRAMES = 57

# References ride along as data URLs, so a 1254x1254 base would inflate every
# request for no gain. The real pipeline's lock is 192x208; this is generous.
REFERENCE_MAX_EDGE = 384

# HOUSE_FORM comes from geist_house so the eval measures the same house form the
# generator asks for. A local copy would drift, and the drift would show up as a
# model looking worse than it is.

PET_DIR = Path.home() / "Desktop/work/geist/pet-design"
SKILL_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def hold_prompt(pose: str) -> str:
    return (
        f"Redraw the exact creature in the attached reference image, unchanged in colour, "
        f"shape, outline, markings and proportion, now {pose}. {HOUSE_FORM} "
        "Centre the character with clear empty space on all four sides."
    )


# The creativity case names no franchise and no character. Everything that makes
# the source recognisable is written as physical description, ranked the way
# identity-blend.md ranks cues: crown cue first, then colour blocks, then one
# prop, then face landmarks.
INVENT_PROMPT = (
    "Draw a new mascot creature in exactly the house style of the attached reference sheet. "
    "Give it: dark brown hair, slightly wavy, falling to just below the ears, with clearly "
    "red-brown tips at the ends; a jagged burn scar on the upper left forehead; a green and "
    "black checkered pattern across the lower body; small rectangular earrings, white with a "
    f"red sun disc. Calm determined expression. {HOUSE_FORM} "
    "Centre the character with clear empty space on all four sides."
)

# --------------------------------------------------------------------------- #
# Concept-sheet cases
# --------------------------------------------------------------------------- #

CAST_LOCKS = [
    "Tall spiked black crest with a sharp widow's peak, flat navy-and-white chest panels with "
    "thin gold trim, narrowed dot eyes and a short flat mouth, no prop.",
    "Round soft orange crest with three blunt forward spikes, flat orange body panel with a "
    "wide blue sash band, wide open dot eyes, one thick rounded staff attached at the side.",
    "Smooth bald dome with six small ink dots in two rows across the crown, flat orange and "
    "yellow robe panels, calm level dot eyes, no prop.",
    "Twin blunt antenna tabs curving back from the crown, flat pale green body tint, one thick "
    "rounded halo ring attached above the dome, gentle upturned mouth.",
    "Wide flat mushroom-shaped lavender crest, flat purple body panel with a white collar block, "
    "half-lidded dot eyes, one thick rounded fan prop attached at the side.",
    "Short bristled teal crest with one thick forward horn tab, flat teal and cream body blocks, "
    "one round cheek dot on each side, no prop.",
]

VARIANT_LOCKS = [
    "Same character, rounder and softer: wide low dome, generous cheek area, the crest reduced "
    "to two soft blunt tabs, calm dot eyes.",
    "Same character, taller and sharper: narrow upright body, the crest raised into three clean "
    "angular spikes, alert dot eyes.",
    "Same character, wider and heavier: broad low body, the crest spread flat and wide, one "
    "thick rounded prop attached low at the side.",
    "Same character, minimal: the crest reduced to a single bold shape and every secondary cue "
    "dropped, relying on silhouette alone.",
]

# The order probe. Each cell is separated from its neighbours by one robust,
# machine-readable statistic -- the dominant saturated hue of its body panel --
# stepping evenly around the hue wheel in cell order.
#
# Counting shapes (horns, dots, spikes) was the obvious design and is the wrong
# one: connected-component counts on generated art confound with the eyes, the
# outline and any prop, so a miscount would say more about the counter than the
# model. A body panel's dominant hue is one number, it survives the chroma path,
# and it is unambiguous at any cell size.
# No cyan, and nothing between 185 and 215 degrees: the house Sky outline is
# #2FB8EC, which sits at about 197. A cyan body panel would be indistinguishable
# from the outline every Pet already has, and the probe would report a model
# error that is really a palette error in this file.
ORDER_HUES = [
    (0, "red"), (40, "orange"), (80, "yellow-green"),
    (130, "green"), (265, "indigo"), (310, "magenta"),
]
ORDER_LOCKS = [
    f"Flat {name} body panel filling most of the body area, plain rounded dome with no crest, "
    f"no prop, calm dot eyes. The body panel is clearly and unmistakably {name}."
    for _hue, name in ORDER_HUES
]


def sheet_case(
    identifier: str,
    locks: list[str],
    references: list[Path],
    difficulty: str,
    order_hues: list[tuple[int, str]] | None = None,
) -> dict[str, Any]:
    columns, rows, aspect_ratio = layout_for(len(locks))
    return {
        "id": identifier,
        "kind": "concept-sheet",
        "references": references,
        "prompt": build_sheet_prompt(locks, columns, rows, len(references) > 1, ""),
        "cues": f"{len(locks)} cells, {columns}x{rows}",
        "difficulty": difficulty,
        "grid": {"columns": columns, "rows": rows, "cell_count": len(locks), "aspect_ratio": aspect_ratio},
        "locks": locks,
        "order_hues": order_hues,
    }


HOUSE_SHEET = SKILL_ASSETS / "geist-house-style.jpg"
DBZ_BASE = PET_DIR / "DragonBallConcepts.pet/sources/canonical-base.png"
HXH_BASE = PET_DIR / "HunterXHunterGeistConcepts.pet/sources/canonical-base.png"
DORAEMON = PET_DIR / "DoraemonGeist.pet/frames/idle/00.png"

SHEET_CASES: tuple[dict[str, Any], ...] = (
    sheet_case("cast-derived-6", CAST_LOCKS, [DBZ_BASE, HOUSE_SHEET],
               "six nameable characters at cell size, identity reference attached"),
    sheet_case("cast-original-6", CAST_LOCKS, [HOUSE_SHEET],
               "invention without collapse -- do six cells become six copies?"),
    sheet_case("variants-single-4", VARIANT_LOCKS, [DORAEMON, HOUSE_SHEET],
               "one character, four stylings, house form constant across cells"),
    sheet_case("order-count-6", ORDER_LOCKS, [HOUSE_SHEET],
               "row-major order, read mechanically from body hue", ORDER_HUES),
    sheet_case("cast-derived-3", CAST_LOCKS[:3], [HXH_BASE, HOUSE_SHEET],
               "3 cells on a 2x2 grid -- is the spare rect left empty, and do "
               "baselines survive composing around a hole?"),
    sheet_case("cast-derived-12", CAST_LOCKS * 2, [DBZ_BASE, HOUSE_SHEET],
               "stress: where cell fidelity breaks, and whether the 12-cell cap holds"),
)

SHEET_CASE_IDS = {case["id"] for case in SHEET_CASES}


TEST_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "doraemon",
        "kind": "identity-hold",
        "reference": PET_DIR / "DoraemonGeist.pet/frames/idle/00.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave"),
        "cues": "round blue head, cream face, collar and bell, whiskers, red nose",
        "difficulty": "medium",
    },
    {
        "id": "gon-hxh",
        "kind": "identity-hold",
        "reference": PET_DIR / "HunterXHunterGeistConcepts.pet/sources/canonical-base.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave, still holding its prop"),
        "cues": "green spiky hair, green and red jacket blocks, fishing rod",
        "difficulty": "hard -- one attached prop",
    },
    {
        "id": "vegeta-dbz",
        "kind": "identity-hold",
        "reference": PET_DIR / "DragonBallConcepts.pet/sources/canonical-base.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave"),
        "cues": "black widow's-peak spiky hair, blue and white armour, gold trim, angry brows",
        "difficulty": "hardest -- spiky hair silhouette",
    },
    {
        "id": "invent-slayer",
        "kind": "creativity",
        "reference": SKILL_ASSETS / "geist-house-style.jpg",
        "prompt": INVENT_PROMPT,
        "cues": "red-tipped dark hair, forehead scar, green/black check, sun-disc earrings",
        "difficulty": "creativity -- no character reference",
    },
    *SHEET_CASES,
)


# --------------------------------------------------------------------------- #
# Spend guard
# --------------------------------------------------------------------------- #


class EvalGuard:
    """Independent of the key's server-side limit, on purpose.

    The key cap stops requests before they reach a provider. This stops the eval
    before a pathological model burns the budget on fallbacks, which is a
    different failure and deserves its own control.
    """

    def __init__(self, max_images: int, max_cost_usd: float) -> None:
        self.max_images = max_images
        self.max_cost_usd = max_cost_usd
        self.images = 0
        self.cost = 0.0

    def check(self) -> None:
        if self.images >= self.max_images:
            raise SystemExit(f"stopped at the --max-images ceiling of {self.max_images}")
        if self.cost >= self.max_cost_usd:
            raise SystemExit(
                f"stopped at the --max-cost-usd ceiling of ${self.max_cost_usd:.2f} "
                f"after {self.images} calls"
            )

    def record(self, cost: float) -> None:
        self.images += 1
        self.cost += cost


# --------------------------------------------------------------------------- #
# Mechanical QA and the silhouette test
# --------------------------------------------------------------------------- #


@dataclass
class Attempt:
    model: str
    case: str
    ok: bool = False
    error: str | None = None
    duration_s: float = 0.0
    cost_usd: float = 0.0
    calls: int = 0
    alpha_path: str = "-"
    width: int = 0
    height: int = 0
    mechanical_pass: bool = False
    reasons: list[str] = field(default_factory=list)
    preview: str | None = None
    silhouette: str | None = None
    sheet: dict[str, Any] | None = None

    def row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "model": self.model,
            "case": self.case,
            "ok": self.ok,
            "error": self.error,
            "duration_s": round(self.duration_s, 2),
            "cost_usd": round(self.cost_usd, 6),
            "calls": self.calls,
            "alpha_path": self.alpha_path,
            "size": [self.width, self.height],
            "mechanical_pass": self.mechanical_pass,
            "reasons": self.reasons,
        }
        if self.sheet is not None:
            row["sheet"] = self.sheet
        return row


def mechanical_score(image: Image.Image) -> tuple[bool, list[str]]:
    """Auto-score what the rubric can check without a human.

    Identity is deliberately absent. Failing here eliminates a candidate before
    it costs anyone their attention; passing earns a human look, not a pass.
    """
    reasons: list[str] = []
    if not alpha_is_real(image):
        reasons.append("no real transparency")

    box = alpha_bbox(image)
    if box is None:
        return False, ["fully transparent: no subject found"]

    left, upper, right, lower = box
    width, height = image.size
    if left <= 0 or upper <= 0 or right >= width or lower >= height:
        reasons.append("subject touches the canvas edge")

    covered = ((right - left) * (lower - upper)) / float(width * height)
    if covered < 0.10:
        reasons.append(f"subject fills only {covered:.0%} of the canvas")
    if covered > 0.95:
        reasons.append(f"subject fills {covered:.0%} of the canvas: no margin")

    return not reasons, reasons


# --------------------------------------------------------------------------- #
# Concept-sheet measurements
# --------------------------------------------------------------------------- #

SKY_HUE_BAND = (185, 215)  # the house outline; never a body-panel signal
SUBJECT_TOLERANCE = 44


def paper_colour(image: Image.Image) -> tuple[int, int, int]:
    """The sheet's background, read off its own border.

    A sheet is opaque by design, so there is no alpha channel to find subjects
    with. The border is the one region guaranteed to be paper -- a mascot that
    reached it would already have failed containment.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    samples = [pixels[x, 0] for x in range(0, width, max(1, width // 64))]
    samples += [pixels[x, height - 1] for x in range(0, width, max(1, width // 64))]
    samples += [pixels[0, y] for y in range(0, height, max(1, height // 64))]
    samples += [pixels[width - 1, y] for y in range(0, height, max(1, height // 64))]
    return (
        round(statistics.median(sample[0] for sample in samples)),
        round(statistics.median(sample[1] for sample in samples)),
        round(statistics.median(sample[2] for sample in samples)),
    )


def subject_mask(cell: Image.Image, paper: tuple[int, int, int]) -> Image.Image:
    difference = ImageChops.difference(cell.convert("RGB"), Image.new("RGB", cell.size, paper))
    return difference.convert("L").point(lambda value: 255 if value > SUBJECT_TOLERANCE else 0)


def dominant_hue(cell: Image.Image, paper: tuple[int, int, int]) -> float | None:
    """The strongest saturated hue in a cell, in degrees, ignoring the outline.

    Only the order probe uses this. Every other sheet metric is geometric.
    """
    hsv = cell.convert("RGB").convert("HSV")
    mask = subject_mask(cell, paper)
    buckets = [0] * 36
    for (hue, saturation, value), flag in zip(hsv.getdata(), mask.getdata()):
        if not flag or saturation < 90 or value < 60:
            continue
        degrees = hue * 360 / 256
        if SKY_HUE_BAND[0] <= degrees <= SKY_HUE_BAND[1]:
            continue
        buckets[int(degrees // 10) % 36] += 1
    if not any(buckets):
        return None
    return (buckets.index(max(buckets)) * 10) + 5


def hue_distance(left: float, right: float) -> float:
    gap = abs(left - right) % 360
    return min(gap, 360 - gap)


def sheet_score(
    image: Image.Image, grid: dict[str, Any], order_hues: list[tuple[int, str]] | None
) -> tuple[bool, list[str], dict[str, Any]]:
    """Score a sheet on whether its cells are comparable.

    A single mascot is scored on identity. A sheet is scored on comparability,
    because comparability is the only reason to draw the cells in one call rather
    than separately -- and it is the one property that cannot be recovered later.
    """
    columns, rows = int(grid["columns"]), int(grid["rows"])
    expected = int(grid["cell_count"])
    paper = paper_colour(image)
    rects = cell_rects(image.width, image.height, columns, rows)

    reasons: list[str] = []
    cells: list[dict[str, Any]] = []
    heights: list[float] = []
    baselines: list[float] = []

    for position in range(1, expected + 1):
        cell = image.crop(rects[position - 1])
        box = subject_mask(cell, paper).getbbox()
        record: dict[str, Any] = {"cell_id": cell_id(position)}
        if box is None:
            record.update(occupied=False, contained=False)
            cells.append(record)
            continue

        left, upper, right, lower = box
        area = ((right - left) * (lower - upper)) / float(cell.width * cell.height)
        # One pixel of slack: a mascot that reaches the exact boundary has almost
        # certainly continued into the next cell, and the crop will clip it.
        contained = left > 1 and upper > 1 and right < cell.width - 1 and lower < cell.height - 1
        record.update(
            occupied=area > 0.03,
            contained=contained,
            coverage=round(area, 4),
            height_fraction=round((lower - upper) / cell.height, 4),
            baseline_fraction=round(lower / cell.height, 4),
        )
        if record["occupied"]:
            heights.append(record["height_fraction"])
            baselines.append(record["baseline_fraction"])
        cells.append(record)

    drawn = [cell for cell in cells if cell.get("occupied")]
    if len(drawn) != expected:
        reasons.append(f"{len(drawn)} of {expected} cells hold a mascot")
    crossing = [cell["cell_id"] for cell in drawn if not cell["contained"]]
    if crossing:
        reasons.append(f"crosses its cell: {', '.join(crossing)}")

    # Comparability, as two numbers. Coefficient of variation for size, plain
    # spread for baseline, both as a fraction of cell height so they mean the
    # same thing on a 3x1 sheet and a 4x3 one.
    scale_cv = (statistics.pstdev(heights) / statistics.fmean(heights)) if len(heights) > 1 else 0.0
    baseline_spread = (max(baselines) - min(baselines)) if len(baselines) > 1 else 0.0
    if scale_cv > 0.18:
        reasons.append(f"cell sizes vary by {scale_cv:.0%}: not comparable")
    if baseline_spread > 0.15:
        reasons.append(f"baselines spread over {baseline_spread:.0%} of cell height")

    metrics: dict[str, Any] = {
        "paper": list(paper),
        "cells_drawn": len(drawn),
        "cells_expected": expected,
        "cells_crossing": crossing,
        "scale_cv": round(scale_cv, 4),
        "baseline_spread": round(baseline_spread, 4),
        "cells": cells,
    }

    if order_hues:
        # Rank, not nearest-match.
        #
        # The first version asked which expected hue each cell was closest to.
        # Measured 2026-08-12, that produced three false positives across two
        # correct sheets: the palette steps by 40 degrees in places, models
        # render "magenta" as a pink near 340, and 340 is closer to red at 0 than
        # to magenta at 310. It called a correct sheet broken.
        #
        # What the probe is actually for is ORDER, and order survives every cell
        # being off by 20 or 30 degrees. So the test is that observed hue rises
        # across the cells the way the requested palette does. A swap breaks
        # monotonicity; a colour merely rendered warm does not.
        observed = [dominant_hue(image.crop(rects[i]), paper) for i in range(expected)]
        normalised = [
            # Red at 0 can come back as 355. Nothing else in the palette lives
            # above 340, so fold that tail below zero and red stays lowest.
            (hue - 360 if hue is not None and hue > 340 else hue)
            for hue in observed
        ]
        placement = [
            {"cell_id": cell_id(position), "expected": name, "observed_hue": hue}
            for position, (hue, (_expected, name)) in enumerate(zip(observed, order_hues), start=1)
        ]
        misplaced: list[str] = []
        for position in range(1, expected):
            left, right = normalised[position - 1], normalised[position]
            if left is None or right is None or right <= left:
                misplaced.append(cell_id(position + 1))
        unreadable = [cell_id(i + 1) for i, hue in enumerate(observed) if hue is None]
        metrics["order"] = {
            "placement": placement,
            "misplaced": misplaced,
            "unreadable": unreadable,
            "method": "monotonic hue rank",
        }
        if misplaced:
            reasons.append(f"row-major order broken at {', '.join(misplaced)}")

    return not reasons, reasons, metrics


def silhouette_of(image: Image.Image) -> Image.Image:
    """The silhouette test from identity-blend.md, rendered rather than described.

    Fill the sprite solid and the crown cue and prop shape should still say who
    it is. A blend carried only by surface detail fails here and nowhere else.
    """
    alpha = image.getchannel("A")
    solid = Image.new("RGBA", image.size, (0, 0, 0, 0))
    solid.paste(Image.new("RGBA", image.size, (17, 17, 17, 255)), mask=alpha)
    return solid


def thumbnail(image: Image.Image, edge: int = 192) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.LANCZOS)
    return copy


def load_reference(path: Path) -> str:
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    if max(image.size) > REFERENCE_MAX_EDGE:
        image.thumbnail((REFERENCE_MAX_EDGE, REFERENCE_MAX_EDGE), Image.LANCZOS)
    return data_uri(image)


# --------------------------------------------------------------------------- #
# One measurement, with both fallbacks
# --------------------------------------------------------------------------- #


def unsupported_parameter(error: str) -> bool:
    return "400" in error and "parameter" in error.lower()


def jsonable(value: Any) -> Any:
    """Paths to strings, at any depth. A sheet case carries a list of them."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    return value


def case_references(case: dict[str, Any]) -> list[Path]:
    """Every case sends at least one reference, and a derived sheet sends two."""
    if case.get("references"):
        return list(case["references"])
    return [case["reference"]]


def measure(model: str, case: dict[str, Any], refs: list[str], guard: EvalGuard) -> Attempt:
    attempt = Attempt(model=model, case=case["id"])
    prompt = case["prompt"]
    is_sheet = case["kind"] == "concept-sheet"
    started = time.monotonic()

    def once(config: ProviderConfig, text: str) -> Image.Image:
        guard.check()
        # retries=0: a retry folds provider latency into the duration and makes
        # the number meaningless. A flaky model failing here is a result.
        payload = call_provider(config, text, refs, retries=0)
        image, cost = decode_image(payload)
        guard.record(cost)
        attempt.calls += 1
        attempt.cost_usd += cost
        return image

    try:
        if is_sheet:
            # A sheet asks for warm off-white paper on purpose, so neither the
            # transparency check nor the chroma fallback applies. Running them
            # would spend a second call keying out a background the sheet is
            # supposed to have.
            config = opaque(ProviderConfig(model=model), case["grid"]["aspect_ratio"])
        else:
            config = ProviderConfig(model=model)
        try:
            image = once(config, prompt)
            attempt.alpha_path = "opaque by request" if is_sheet else "native"
        except SystemExit as error:
            if "ceiling" in str(error) or not unsupported_parameter(str(error)):
                raise
            # The model rejects output_format/background outright. Drop them and
            # let the chroma path below deal with the opaque result.
            config = ProviderConfig(model=model, output_format=None, background=None,
                                    aspect_ratio=config.aspect_ratio)
            image = once(config, prompt)
            attempt.alpha_path = "params-dropped"

        if not is_sheet and not alpha_is_real(image):
            image = key_out_chroma(once(config, prompt + CHROMA_SUFFIX))
            attempt.alpha_path = (
                "chroma-key" if attempt.alpha_path == "native" else "params-dropped+chroma"
            )
    except SystemExit as error:
        if "ceiling" in str(error):
            raise
        attempt.duration_s = time.monotonic() - started
        attempt.error = str(error)
        return attempt
    except Exception as error:  # noqa: BLE001 - one model must not end the run
        attempt.duration_s = time.monotonic() - started
        attempt.error = f"{type(error).__name__}: {error}"
        return attempt

    attempt.duration_s = time.monotonic() - started
    attempt.ok = True
    attempt.width, attempt.height = image.size

    if is_sheet:
        attempt.mechanical_pass, attempt.reasons, attempt.sheet = sheet_score(
            image, case["grid"], case.get("order_hues")
        )
        # A sheet is judged as a sheet, so it is shown whole and wide. The
        # silhouette test belongs to one mascot and says nothing about a grid.
        attempt.preview = data_uri(thumbnail(image, 900))
        return attempt

    attempt.mechanical_pass, attempt.reasons = mechanical_score(image)
    attempt.preview = data_uri(thumbnail(image, 320))
    attempt.silhouette = data_uri(thumbnail(silhouette_of(image), 192))
    return attempt


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def summarise(attempts: list[Attempt]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in dict.fromkeys(a.model for a in attempts):
        mine = [a for a in attempts if a.model == model]
        done = [a for a in mine if a.ok]
        passed = [a for a in done if a.mechanical_pass]
        costs = [a.cost_usd for a in done]
        times = [a.duration_s for a in done]

        # A sheet is not a frame and does not cost like one, so it stays out of
        # the 57-frame projection. Folding the two together would quietly move
        # the number the default model was chosen on.
        frame_costs = [a.cost_usd for a in done if a.case not in SHEET_CASE_IDS]
        sheet_costs = [a.cost_usd for a in done if a.case in SHEET_CASE_IDS]
        median_cost = statistics.median(frame_costs) if frame_costs else 0.0
        sheets = [a for a in mine if a.case in SHEET_CASE_IDS]
        sheets_done = [a for a in sheets if a.ok]

        rows.append({
            "model": model,
            "returned": f"{len(done)}/{len(mine)}",
            "mechanical_pass": f"{len(passed)}/{len(mine)}",
            "median_s": round(statistics.median(times), 2) if times else None,
            "total_cost_usd": round(sum(costs), 6),
            "median_cost_usd": round(median_cost, 6),
            "projected_pass_usd": round(median_cost * FULL_PET_FRAMES, 4),
            "median_sheet_usd": round(statistics.median(sheet_costs), 6) if sheet_costs else None,
            "sheets_comparable": (
                f"{sum(1 for a in sheets_done if a.mechanical_pass)}/{len(sheets)}" if sheets else "-"
            ),
            "sheets_order_held": (
                sum(1 for a in sheets_done if a.sheet and a.sheet.get("order")
                    and not a.sheet["order"]["misplaced"])
            ),
            "alpha_paths": sorted({a.alpha_path for a in done}),
            "errors": [a.error for a in mine if a.error],
        })
    rows.sort(key=lambda r: (-int(r["mechanical_pass"].split("/")[0]), r["projected_pass_usd"]))
    return rows


def print_summary(rows: list[dict[str, Any]], guard: EvalGuard) -> None:
    print()
    print(f"{'model':36}{'ret':>5}{'mech':>6}{'med s':>8}{'run $':>9}{'57-frame $':>12}"
          f"{'sheet $':>10}{'compar.':>9}  alpha path")
    print("-" * 124)
    for row in rows:
        median = f"{row['median_s']:.1f}" if row["median_s"] is not None else "-"
        sheet_cost = f"{row['median_sheet_usd']:.4f}" if row["median_sheet_usd"] is not None else "-"
        print(f"{row['model']:36}{row['returned']:>5}{row['mechanical_pass']:>6}{median:>8}"
              f"{row['total_cost_usd']:>9.4f}{row['projected_pass_usd']:>12.2f}"
              f"{sheet_cost:>10}{row['sheets_comparable']:>9}  "
              f"{','.join(row['alpha_paths']) or '-'}")
    print("-" * 124)
    print(f"{guard.images} provider calls, ${guard.cost:.4f} spent")
    print("\n'57-frame $' projects median measured FRAME cost across a full Pet; sheet")
    print("cases are excluded from it because a sheet is not a frame. 'compar.' counts")
    print("sheets whose cells came out comparable -- right count, contained, matched")
    print("scale and baseline, and in row-major order. Mechanical pass is necessary,")
    print("not sufficient: open review.html and judge identity before choosing.")


REVIEW_CSS = """
*{box-sizing:border-box}
body{background:#14161a;color:#e6e6e6;font:14px/1.55 -apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}
p.note{color:#9aa0a6;margin:0 0 20px;max-width:80ch}
.case{margin:0 0 34px;border-top:1px solid #2a2d33;padding-top:18px}
.case h2{font-size:16px;margin:0 0 2px}
.case .meta{color:#9aa0a6;font-size:13px;margin:0 0 14px}
.grid{display:flex;flex-wrap:wrap;gap:14px}
figure{margin:0;background:#1e2126;border-radius:10px;padding:12px;width:252px}
.pair{display:flex;gap:8px;align-items:flex-start}
.pair img{border-radius:6px;
 background-image:linear-gradient(45deg,#2a2d33 25%,transparent 25%,transparent 75%,#2a2d33 75%),
 linear-gradient(45deg,#2a2d33 25%,transparent 25%,transparent 75%,#2a2d33 75%);
 background-size:14px 14px;background-position:0 0,7px 7px}
.pair img.main{width:152px;height:152px;object-fit:contain}
.pair img.sil{width:64px;height:64px;object-fit:contain;background:#fff}
.pair img.sheet{width:100%;object-fit:contain;background:#fff}
figure.sheet{width:640px}
figcaption{font-size:12px;color:#9aa0a6;margin-top:8px;word-break:break-word}
.marks{margin-top:10px;border-top:1px solid #2a2d33;padding-top:8px;font-size:12px}
.marks label{display:block;margin:5px 0 2px;color:#c9ced6}
.marks select{width:100%;background:#14161a;color:#e6e6e6;border:1px solid #3a3f47;border-radius:5px;padding:4px}
.pass{color:#7ee787}.fail{color:#ff7b72}
.err{color:#ff7b72;font-family:ui-monospace,monospace;font-size:12px}
.bar{position:sticky;top:0;background:#14161a;padding:10px 0 14px;z-index:5;border-bottom:1px solid #2a2d33;margin-bottom:18px}
button{background:#2f6feb;color:#fff;border:0;border-radius:7px;padding:9px 16px;font-size:13px;cursor:pointer}
button:hover{background:#4680f0}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;background:#2a2d33;color:#9aa0a6;margin-left:6px}
"""

REVIEW_JS = """
function copyMarks(){
  const out=[];
  document.querySelectorAll('figure[data-model]').forEach(f=>{
    const a=f.querySelector('.m-aes').value, n=f.querySelector('.m-name').value, b=f.querySelector('.m-blend').value;
    if(a==='-'&&n==='-'&&b==='-') return;
    out.push(f.dataset.case+' | '+f.dataset.model+' | aesthetic='+a+' | naming='+n+' | blend='+b);
  });
  const text = out.length ? 'Eval marks:\\n'+out.join('\\n') : 'No marks set yet.';
  navigator.clipboard.writeText(text).then(()=>{
    const b=document.getElementById('copybtn'), o=b.textContent;
    b.textContent='Copied '+out.length+' marks'; setTimeout(()=>{b.textContent=o;},1800);
  });
}
"""


def write_review(attempts: list[Attempt], rows: list[dict[str, Any]], path: Path) -> None:
    """The human half of the score.

    Each candidate shows at thumbnail scale beside its silhouette, because the
    naming test is a thumbnail test and the silhouette test is the one that
    catches a blend carried only by surface detail.
    """
    by_model = {r["model"]: r for r in rows}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Provider eval &mdash; review</title>",
        f"<style>{REVIEW_CSS}</style>",
        "<div class='bar'><button id='copybtn' onclick='copyMarks()'>Copy marks</button></div>",
        "<h1>Provider eval &mdash; identity review</h1>",
        "<p class='note'>Mechanical QA has already run and is shown per candidate. Your job is the "
        "two tests it cannot do. <b>Naming test:</b> at this thumbnail size, can someone who knows "
        "the source name it in about two seconds? <b>Blend verdict:</b> a good blend, or one of the "
        "two failure modes &mdash; <i>franchise copy</i> (the source style won: legs, source outline "
        "colour, heart missing or tacked on) or <i>generic blob</i> (the house form won: not nameable, "
        "cues collapsed). The small white panel is the silhouette test.</p>",
    ]
    for case in TEST_CASES:
        mine = [a for a in attempts if a.case == case["id"]]
        if not mine:
            continue
        parts.append(
            f"<div class='case'><h2>{html.escape(case['id'])}"
            f"<span class='tag'>{html.escape(case['kind'])}</span>"
            f"<span class='tag'>{html.escape(case['difficulty'])}</span></h2>"
            f"<p class='meta'>Cues that must survive: {html.escape(case['cues'])}</p><div class='grid'>"
        )
        for attempt in sorted(mine, key=lambda a: (not a.mechanical_pass, a.model)):
            summary = by_model.get(attempt.model, {})
            parts.append(
                f"<figure class='{'sheet' if attempt.sheet is not None else ''}' "
                f"data-model='{html.escape(attempt.model)}' "
                f"data-case='{html.escape(attempt.case)}'>"
            )
            if attempt.preview and attempt.sheet is not None:
                verdict = ("<span class='pass'>comparable</span>" if attempt.mechanical_pass
                           else "<span class='fail'>"
                                + html.escape("; ".join(attempt.reasons)) + "</span>")
                sheet = attempt.sheet
                order = sheet.get("order")
                order_line = ""
                if order:
                    misplaced = order["misplaced"]
                    order_line = (
                        "<br>order: <span class='pass'>row-major held</span>" if not misplaced
                        else f"<br>order: <span class='fail'>broken at "
                             f"{html.escape(', '.join(misplaced))}</span>"
                    )
                parts.append(
                    f"<div class='pair'><img class='sheet' src='{attempt.preview}' "
                    f"alt='{html.escape(attempt.model)} sheet'></div>"
                    f"<figcaption><b>{html.escape(attempt.model)}</b><br>"
                    f"{attempt.duration_s:.1f}s &middot; ${attempt.cost_usd:.4f} &middot; "
                    f"{attempt.calls} call(s)<br>"
                    f"cells {sheet['cells_drawn']}/{sheet['cells_expected']} &middot; "
                    f"size spread {sheet['scale_cv']:.0%} &middot; "
                    f"baseline spread {sheet['baseline_spread']:.0%}"
                    f"{order_line}<br>{verdict}</figcaption>"
                )
            elif attempt.preview:
                verdict = ("<span class='pass'>mechanical pass</span>" if attempt.mechanical_pass
                           else "<span class='fail'>"
                                + html.escape("; ".join(attempt.reasons)) + "</span>")
                parts.append(
                    f"<div class='pair'><img class='main' src='{attempt.preview}' "
                    f"alt='{html.escape(attempt.model)}'>"
                    f"<img class='sil' src='{attempt.silhouette}' alt='silhouette'></div>"
                    f"<figcaption><b>{html.escape(attempt.model)}</b><br>"
                    f"{attempt.duration_s:.1f}s &middot; ${attempt.cost_usd:.4f} &middot; "
                    f"{attempt.calls} call(s) &middot; {html.escape(attempt.alpha_path)}<br>"
                    f"57-frame ~${summary.get('projected_pass_usd', 0):.2f}<br>{verdict}</figcaption>"
                )
            else:
                parts.append(
                    f"<figcaption><b>{html.escape(attempt.model)}</b><br>"
                    f"<span class='err'>{html.escape(str(attempt.error))}</span></figcaption>"
                )
            parts.append(
                "<div class='marks'>"
                "<label>Aesthetic</label><select class='m-aes'>"
                "<option>-</option><option>1</option><option>2</option><option>3</option>"
                "<option>4</option><option>5</option></select>"
                "<label>Naming test</label><select class='m-name'>"
                "<option>-</option><option>pass</option><option>fail</option></select>"
                "<label>Blend verdict</label><select class='m-blend'>"
                "<option>-</option><option>good</option><option>franchise-copy</option>"
                "<option>generic-blob</option></select></div></figure>"
            )
        parts.append("</div></div>")
    parts.append(f"<script>{REVIEW_JS}</script>")
    path.write_text("".join(parts), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("provider-eval"))
    parser.add_argument("--models", nargs="*", default=list(CONTENDERS))
    parser.add_argument("--cases", nargs="*", default=[c["id"] for c in TEST_CASES])
    parser.add_argument("--max-images", type=int, default=140,
                        help="Hard ceiling on provider calls, fallbacks included. Ten cases across "
                             "seven contenders is 70 calls before fallbacks; the four "
                             "identity cases mostly need a second call, the six sheets never do.")
    parser.add_argument("--max-cost-usd", type=float, default=6.0,
                        help="Hard ceiling on spend, independent of the key's own limit. Raised "
                             "from $4.50 for the sheet cases: a sheet needs more pixels than a "
                             "192x208 frame, so its per-image price is not yet known to sit in "
                             "the $0.0175-$0.0243 band the 2026-08-12 eval measured.")
    parser.add_argument("--base-url", help="Provider base URL; point at a mock to spend nothing")
    args = parser.parse_args()

    set_base_url(args.base_url)
    api_key()
    print(f"endpoint: {endpoint()}")

    cases = [c for c in TEST_CASES if c["id"] in args.cases]
    missing = [str(path) for c in cases for path in case_references(c) if not path.is_file()]
    if missing:
        raise SystemExit("missing reference art:\n  " + "\n  ".join(missing))

    guard = EvalGuard(args.max_images, args.max_cost_usd)
    print(f"{len(args.models)} models x {len(cases)} cases = {len(args.models) * len(cases)} frames "
          f"(plus fallback calls)")
    print(f"ceilings: {args.max_images} calls, ${args.max_cost_usd:.2f}\n")

    attempts: list[Attempt] = []
    stopped = None
    # Case-major: if a ceiling fires you get complete model comparisons for the
    # finished cases rather than gaps spread across all of them.
    for case in cases:
        print(f"--- {case['id']} ({case['kind']}, {case['difficulty']})")
        refs = [load_reference(path) for path in case_references(case)]
        for model in args.models:
            print(f"  {model:36} ", end="", flush=True)
            try:
                attempt = measure(model, case, refs, guard)
            except SystemExit as stop:
                stopped = str(stop)
                print(f"\n{stop}")
                break
            attempts.append(attempt)
            if attempt.ok:
                print(f"{attempt.duration_s:6.1f}s ${attempt.cost_usd:.4f} {attempt.calls}c "
                      f"{attempt.alpha_path:22} "
                      f"{'pass' if attempt.mechanical_pass else 'MECH FAIL'}")
            else:
                print(f"failed: {str(attempt.error)[:80]}")
        if stopped:
            break

    if not attempts:
        raise SystemExit("no measurements taken")

    args.out.mkdir(parents=True, exist_ok=True)
    rows = summarise(attempts)
    (args.out / "results.json").write_text(json.dumps({
        "cases": [{key: jsonable(value) for key, value in c.items()} for c in cases],
        "calls": guard.images,
        "cost_usd": round(guard.cost, 6),
        "stopped_early": stopped,
        "summary": rows,
        "attempts": [a.row() for a in attempts],
    }, indent=2), encoding="utf-8")
    write_review(attempts, rows, args.out / "review.html")
    print_summary(rows, guard)
    if stopped:
        print(f"\nSTOPPED EARLY: {stopped}")
    print(f"\nwrote {args.out / 'results.json'} and {args.out / 'review.html'}")


if __name__ == "__main__":
    main()
