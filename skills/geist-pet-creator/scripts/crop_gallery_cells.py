#!/usr/bin/env python3
"""Cut chosen cells out of an approved concept sheet.

The grid comes from the packet's own `candidate-context.json`, not from a flag,
so the cut matches the grid that was actually requested rather than the one
someone remembers requesting.

The grid is where the cut goes, but an even grid is what the sheet was ASKED
for, not always what came back. Measured 2026-08-12: `openai/gpt-image-2` drew a
4x3 sheet whose first row of mascots ran 20 pixels past the even-thirds
boundary, so an even cut would have shaved the bottom of every one of them --
quietly, and on the outline. So the cut snaps to the gutters between the drawn
rows when they are unambiguous, and falls back to the even grid, loudly, when
they are not.

Two things this deliberately does not do:

**It does not trim the paper.** A sheet is drawn on warm off-white, and trimming
that away needs a threshold tight against the mascot. Pick it slightly wrong and
it eats the Sky outline, which is the one part of the house form a cell cannot
lose. Snapping to a gutter is a different measurement -- it looks for empty
paper BETWEEN mascots, far from any outline. A cell becomes Image 1 of a
canonical-base call, and a reference image does not need to be tight or
transparent; it needs to be honest.

**It does not scaffold bundles.** Naming a Pet, writing its brief and deciding
which cells become Pets at all are judgement calls. This writes crops; the agent
decides what they are for.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from geist_house import bands_to_rects, cell_rects, detect_bands

SUBJECT_TOLERANCE = 44


def subject_mask(image: Image.Image) -> Image.Image:
    """Everything that is not paper, as a 1-bit mask.

    Paper is read off the sheet's own border, which is the one region guaranteed
    to be background: a mascot that reached it would already have failed
    containment at pre-screen.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    border = (
        [pixels[x, 0] for x in range(0, width, max(1, width // 64))]
        + [pixels[x, height - 1] for x in range(0, width, max(1, width // 64))]
        + [pixels[0, y] for y in range(0, height, max(1, height // 64))]
        + [pixels[width - 1, y] for y in range(0, height, max(1, height // 64))]
    )
    paper = tuple(sorted(channel)[len(border) // 2] for channel in zip(*border))
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, paper))
    return difference.convert("L").point(lambda value: 255 if value > SUBJECT_TOLERANCE else 0)


def resolve_rects(
    sheet: Image.Image, columns: int, rows: int
) -> tuple[list[tuple[int, int, int, int]], str, str | None]:
    """Cut lines for this sheet, snapped to the drawn gutters where possible."""
    row_bands, column_bands = detect_bands(subject_mask(sheet), columns, rows)
    if row_bands and column_bands:
        return bands_to_rects(sheet.width, sheet.height, row_bands, column_bands), "snapped-to-gutters", None
    axes = ", ".join(
        axis for axis, found in (("rows", row_bands), ("columns", column_bands)) if not found
    )
    return (
        cell_rects(sheet.width, sheet.height, columns, rows),
        "even-grid",
        f"could not read the drawn {axes} -- mascots may be touching across the gutter. "
        f"Cut on the even grid instead; check the crops for clipped outlines.",
    )

CELL_ID = re.compile(r"^(?:cell-)?(\d{1,2})$")


def find_packet(bundle: Path, candidate_id: str | None) -> Path:
    """The concept-sheet packet to cut from."""
    candidates = bundle / "sources" / "candidates"
    if candidate_id:
        packet = candidates / candidate_id
        if not (packet / "candidate-context.json").is_file():
            raise SystemExit(f"{packet}/candidate-context.json does not exist")
        return packet

    sheets = sorted(
        path.parent
        for path in candidates.glob("*/candidate-context.json")
        if json.loads(path.read_text(encoding="utf-8")).get("target", {}).get("kind") == "concept-sheet"
    )
    if not sheets:
        raise SystemExit(f"no concept-sheet packet under {candidates}; draw one first")
    if len(sheets) > 1 and not candidate_id:
        names = ", ".join(sheet.name for sheet in sheets)
        print(f"note: {len(sheets)} sheets present ({names}); using {sheets[-1].name}")
    return sheets[-1]


def parse_cells(spec: str | None, cell_count: int) -> list[int]:
    """`4`, `cell-04`, `2,5` and `1-3` all mean the obvious thing. 1-based."""
    if not spec:
        return list(range(1, cell_count + 1))
    wanted: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk and not chunk.lower().startswith("cell-"):
            low, high = chunk.split("-", 1)
            wanted.extend(range(int(low), int(high) + 1))
            continue
        match = CELL_ID.match(chunk.lower())
        if not match:
            raise SystemExit(f"cannot read cell '{chunk}'; use 4, cell-04, 2,5 or 1-3")
        wanted.append(int(match.group(1)))

    numbers = sorted(set(wanted))
    outside = [number for number in numbers if not 1 <= number <= cell_count]
    if outside:
        raise SystemExit(f"cells {outside} are outside this sheet, which has {cell_count} cells")
    return numbers


def verdict_map(context: dict[str, Any]) -> dict[str, str]:
    pre_screen = context.get("agent_pre_screen", {})
    entries = pre_screen.get("cells", []) if isinstance(pre_screen, dict) else []
    return {
        str(entry.get("cell_id")): str(entry.get("status", "pending"))
        for entry in entries
        if isinstance(entry, dict)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", help="Path to the bundle holding the concept-sheet packet")
    parser.add_argument("--candidate-id", help="Packet to cut from; defaults to the newest concept sheet")
    parser.add_argument("--cells", help="Which cells: 4, cell-04, 2,5 or 1-3. Defaults to every cell")
    parser.add_argument("--output-dir", help="Where crops land; defaults to <packet>/cells/")
    parser.add_argument("--even-grid", action="store_true",
                        help="Cut on exact even thirds instead of snapping to the drawn gutters. "
                             "Only useful when the snap picks the wrong lines.")
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    packet = find_packet(bundle, args.candidate_id)
    context = json.loads((packet / "candidate-context.json").read_text(encoding="utf-8"))

    grid = context.get("grid") or {}
    columns, rows = int(grid.get("columns") or 0), int(grid.get("rows") or 0)
    cell_count = int(grid.get("cell_count") or 0)
    if not (columns and rows and cell_count):
        raise SystemExit(
            f"{packet}/candidate-context.json has no usable `grid`. It records the grid that was "
            "requested, and without it there is no way to know where cell 4 is."
        )

    sheet_path = bundle / str(context.get("generated_file") or "")
    if not sheet_path.is_file():
        sheet_path = packet / "candidate.png"
    if not sheet_path.is_file():
        raise SystemExit(f"no sheet image found for {packet.name}")

    wanted = parse_cells(args.cells, cell_count)
    verdicts = verdict_map(context)

    refused = [f"cell-{number:02d}" for number in wanted if verdicts.get(f"cell-{number:02d}") == "fail"]
    if refused:
        raise SystemExit(
            f"{', '.join(refused)} failed pre-screen, so {'it is' if len(refused) == 1 else 'they are'} "
            f"not choosable. Redraw the sheet, or pick a cell that passed."
        )

    sheet = Image.open(sheet_path).convert("RGBA")
    if args.even_grid:
        rects, cut_method, warning = cell_rects(sheet.width, sheet.height, columns, rows), "even-grid", None
    else:
        rects, cut_method, warning = resolve_rects(sheet, columns, rows)
    if warning:
        print(f"warning: {warning}")
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else packet / "cells"
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, Any]] = []
    for number in wanted:
        identifier = f"cell-{number:02d}"
        rect = rects[number - 1]
        crop = sheet.crop(rect)
        destination = output_dir / f"{identifier}.png"
        crop.save(destination)
        written.append(
            {
                "cell_id": identifier,
                "path": str(destination),
                "rect": list(rect),
                "size": list(crop.size),
                "pre_screen": verdicts.get(identifier, "pending"),
            }
        )

    unscreened = [entry["cell_id"] for entry in written if entry["pre_screen"] == "pending"]
    print(
        json.dumps(
            {
                "ok": True,
                "candidate_id": context.get("candidate_id", packet.name),
                "sheet": str(sheet_path),
                "grid": {"columns": columns, "rows": rows, "cell_count": cell_count},
                "cut_method": cut_method,
                "cut_warning": warning,
                "cells": written,
                "unscreened": unscreened,
                "next": (
                    "carry each crop into the canonical-base gate as Image 1 -- a cell is a "
                    "concept, and only a sprite-scale candidate approved at that gate becomes "
                    "sources/canonical-base.png"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
