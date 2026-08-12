#!/usr/bin/env python3
"""Audit every frame of a Geist Pet atlas for anatomy drift.

Anatomy drift is a part of the Pet going missing, appearing twice, or crossing
the cell line. Geometry checks stay silent on all three, so this script produces
evidence and ranks frames by suspicion; a human and an agent supply the verdicts.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from export_geist_pet import atlas_digest, compose_atlas
from geist_grid import (
    ARTWORK_CELLS,
    ATLAS_HEIGHT,
    ATLAS_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    EMPTY_CELLS,
    ROW_SPECS,
    FrameGrid,
    cell_box,
)
from geist_manifest import PartManifest, read_manifest
from geist_pixels import ALPHA_THRESHOLD, alpha_bbox, alpha_mask, clear_transparent_rgb, data_uri
import geist_registration as registration

MAX_REPAIR_PASSES = 2
# Lanczos resampling spreads an edge by roughly one pixel.
RESAMPLE_BLEED = 1
STRAY_COMPONENT_RATIO = 0.02
MIN_COMPONENT_AREA = 12
SUSPICION_FLAG = 45


# --------------------------------------------------------------------------- #
# Measuring a cell, once
# --------------------------------------------------------------------------- #


@dataclass
class CellMeasurement:
    """Everything the signals need from one cell, computed in a single pass.

    Each signal used to walk the pixels again. They now share this.
    """

    empty: bool
    mask: bytearray = field(default_factory=bytearray)
    area: int = 0
    bbox: tuple[int, int, int, int] | None = None
    main_bbox: tuple[int, int, int, int] | None = None
    main_area: int = 0
    components: list[dict[str, Any]] = field(default_factory=list)
    stray_ratio: float = 0.0
    asymmetry: float = 0.0
    edge_contact: list[str] = field(default_factory=list)

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def component_areas(self) -> list[int]:
        return [component["area"] for component in self.components]


def components(mask: bytearray, width: int, height: int) -> list[dict[str, Any]]:
    """4-connected components, largest first, tiny specks dropped."""
    seen = bytearray(width * height)
    found: list[dict[str, Any]] = []
    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        pixels: list[int] = []
        while stack:
            index = stack.pop()
            pixels.append(index)
            x = index % width
            y = index // width
            if x > 0 and mask[index - 1] and not seen[index - 1]:
                seen[index - 1] = 1
                stack.append(index - 1)
            if x < width - 1 and mask[index + 1] and not seen[index + 1]:
                seen[index + 1] = 1
                stack.append(index + 1)
            if y > 0 and mask[index - width] and not seen[index - width]:
                seen[index - width] = 1
                stack.append(index - width)
            if y < height - 1 and mask[index + width] and not seen[index + width]:
                seen[index + width] = 1
                stack.append(index + width)
        if len(pixels) < MIN_COMPONENT_AREA:
            continue
        xs = [index % width for index in pixels]
        ys = [index // width for index in pixels]
        found.append(
            {
                "area": len(pixels),
                "bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1],
                "pixels": pixels,
            }
        )
    found.sort(key=lambda component: -component["area"])
    return found


def measure_cell(cell: Image.Image) -> CellMeasurement:
    mask = alpha_mask(cell)
    found = components(mask, CELL_WIDTH, CELL_HEIGHT)
    if not found:
        return CellMeasurement(empty=True, mask=mask)

    main = found[0]
    left = min(component["bbox"][0] for component in found)
    top = min(component["bbox"][1] for component in found)
    right = max(component["bbox"][2] for component in found)
    bottom = max(component["bbox"][3] for component in found)

    half = CELL_WIDTH // 2
    left_area = 0
    for y in range(CELL_HEIGHT):
        row = y * CELL_WIDTH
        left_area += sum(mask[row : row + half])
    total_area = sum(mask)

    touching = []
    if left <= 0:
        touching.append("left")
    if top <= 0:
        touching.append("top")
    if right >= CELL_WIDTH:
        touching.append("right")
    if bottom >= CELL_HEIGHT:
        touching.append("bottom")

    stray_area = sum(component["area"] for component in found[1:])
    return CellMeasurement(
        empty=False,
        mask=mask,
        area=total_area,
        bbox=(left, top, right, bottom),
        main_bbox=tuple(main["bbox"]),
        main_area=main["area"],
        components=found,
        stray_ratio=round(stray_area / main["area"], 4) if main["area"] else 0.0,
        asymmetry=round((left_area - (total_area - left_area)) / total_area, 4) if total_area else 0.0,
        edge_contact=touching,
    )


def diff_ratio(mask_a: bytearray, mask_b: bytearray) -> float:
    differing = 0
    covered = 0
    for here, there in zip(mask_a, mask_b):
        if here or there:
            covered += 1
            if here != there:
                differing += 1
    return round(differing / covered, 4) if covered else 0.0


# --------------------------------------------------------------------------- #
# Suspicion ranking
# --------------------------------------------------------------------------- #


def suspicion_score(signals: dict[str, Any]) -> int:
    """Rank a frame by how much it deserves the agent's attention.

    Advisory only. A low score never means a frame is correct; it means the
    measurable signals found nothing to point at.
    """
    score = 0.0
    score += min(40.0, signals["bbox_delta"] * 1.2)
    score += min(25.0, abs(signals["area_delta_ratio"]) * 100.0)
    score += min(20.0, max(0, signals["component_count"] - 1) * 10.0)
    score += min(20.0, signals["stray_ratio"] * 400.0)
    score += min(20.0, abs(signals["asymmetry_delta"]) * 120.0)
    score += min(25.0, signals["diff_ratio"] * 60.0)
    return int(min(100.0, score))


# --------------------------------------------------------------------------- #
# Deterministic repair
# --------------------------------------------------------------------------- #


def repair_log_path(bundle: Path) -> Path:
    return bundle / "qa" / "repair-log.json"


def load_repair_log(bundle: Path) -> dict[str, int]:
    path = repair_log_path(bundle)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_repair_log(bundle: Path, log: dict[str, int]) -> None:
    path = repair_log_path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def back_up_frame(bundle: Path, frame_path: Path, state: str, index: int, passes: int) -> Path:
    backup_dir = bundle / "sources" / "raw" / "repair-backups" / state
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{index:02d}-pass{passes}.png"
    shutil.copy2(frame_path, backup)
    return backup


def deterministic_repair(
    image: Image.Image, measurement: CellMeasurement, safe_padding: int
) -> tuple[Image.Image, list[str]]:
    """Move or clear pixels that already exist. Never invent artwork."""
    applied: list[str] = []
    repaired = clear_transparent_rgb(image)
    if repaired.tobytes() != image.tobytes():
        applied.append("cleared transparent RGB residue")

    if measurement.component_count > 1:
        pixels = bytearray(repaired.tobytes())
        main_area = measurement.main_area
        dropped = 0
        for component in measurement.components[1:]:
            if component["area"] <= STRAY_COMPONENT_RATIO * main_area:
                for index in component["pixels"]:
                    base = index * 4
                    pixels[base] = pixels[base + 1] = pixels[base + 2] = pixels[base + 3] = 0
                dropped += 1
        if dropped:
            repaired = Image.frombytes("RGBA", repaired.size, bytes(pixels))
            applied.append(f"removed {dropped} detached fragment(s) under {STRAY_COMPONENT_RATIO:.0%} of the body")

    if measurement.edge_contact and measurement.bbox:
        left, top, right, bottom = measurement.bbox
        shift_x = 0
        shift_y = 0
        # Shift an axis only when the body actually fits along it. A body wider
        # than the safe box has no offset that puts it inside, and the earlier
        # if/elif took the `left` branch anyway -- pushing the sprite FURTHER off
        # the right edge, then reporting a successful repair and burning a pass.
        # A body that does not fit needs `refit_state`, not a translation.
        if right - left <= CELL_WIDTH - 2 * safe_padding:
            if left < safe_padding:
                shift_x = safe_padding - left
            elif right > CELL_WIDTH - safe_padding:
                shift_x = (CELL_WIDTH - safe_padding) - right
        if bottom - top <= CELL_HEIGHT - 2 * safe_padding:
            if top < safe_padding:
                shift_y = safe_padding - top
            elif bottom > CELL_HEIGHT - safe_padding:
                shift_y = (CELL_HEIGHT - safe_padding) - bottom
        if shift_x or shift_y:
            moved = Image.new("RGBA", repaired.size, (0, 0, 0, 0))
            moved.paste(repaired, (shift_x, shift_y))
            repaired = moved
            applied.append(f"shifted the body {shift_x:+d},{shift_y:+d} back inside {safe_padding}px safe padding")

    return repaired, applied


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


@dataclass
class AuditResult:
    payload: dict[str, Any]
    cell_images: dict[str, Image.Image] = field(default_factory=dict)
    anchor_images: dict[str, Image.Image] = field(default_factory=dict)


def audit_atlas(
    atlas: Image.Image,
    grid: FrameGrid,
    *,
    manifest: PartManifest,
    safe_padding: int,
    source: str,
) -> AuditResult:
    errors: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    cell_images: dict[str, Image.Image] = {}
    anchor_images: dict[str, Image.Image] = {}

    for state, row, frame_count in ROW_SPECS:
        measured = []
        for column in range(8):
            cell = atlas.crop(cell_box(row, column))
            measured.append((column, cell, measure_cell(cell)))

        # The 15 cells past a state's frame count carry no artwork. A script
        # settles them; agent attention belongs on the 57 that hold a Pet.
        for column, _cell, measurement in measured[frame_count:]:
            if not measurement.empty:
                errors.append(
                    {
                        "code": "unused_cell_not_empty",
                        "state": state,
                        "column": column,
                        "path": f"atlas row {row} column {column}",
                        "message": (
                            f"{state} column {column} must be fully transparent; "
                            f"found {measurement.area} visible pixels"
                        ),
                    }
                )

        artwork = measured[:frame_count]
        filled = [item for item in artwork if not item[2].empty]
        if not filled:
            for column, _cell, _measurement in artwork:
                errors.append(
                    {
                        "code": "empty_artwork_cell",
                        "state": state,
                        "column": column,
                        "path": grid.label(state, column),
                        "message": f"{state} frame {column} has no visible pixels",
                    }
                )
            continue

        # The anchor frame is the state's most typical frame by visible area.
        # Every other frame in the state is measured against it.
        ordered = sorted(filled, key=lambda item: item[2].area)
        anchor_column, anchor_cell, anchor = ordered[len(ordered) // 2]
        anchor_images[state] = anchor_cell

        for column, cell, measurement in artwork:
            label = grid.label(state, column)
            cell_images[label] = cell

            if measurement.empty:
                errors.append(
                    {
                        "code": "empty_artwork_cell",
                        "state": state,
                        "column": column,
                        "path": label,
                        "message": f"{state} frame {column} has no visible pixels",
                    }
                )
                frames.append(
                    {
                        "path": label,
                        "state": state,
                        "column": column,
                        "empty": True,
                        "suspicion": 100,
                        "hard_errors": ["empty_artwork_cell"],
                        "agent_verdict": None,
                    }
                )
                continue

            signals = {
                "bbox_delta": max(abs(measurement.bbox[i] - anchor.bbox[i]) for i in range(4)),
                "area_delta_ratio": round((measurement.area - anchor.area) / anchor.area, 4) if anchor.area else 0.0,
                "component_count": measurement.component_count,
                "component_areas": measurement.component_areas,
                "stray_ratio": measurement.stray_ratio,
                "asymmetry": measurement.asymmetry,
                "asymmetry_delta": round(measurement.asymmetry - anchor.asymmetry, 4),
                "diff_ratio": diff_ratio(measurement.mask, anchor.mask),
            }

            hard_errors: list[str] = []
            if measurement.edge_contact:
                hard_errors.append("cell_bleed")
                errors.append(
                    {
                        "code": "cell_bleed",
                        "state": state,
                        "column": column,
                        "path": label,
                        "message": (
                            f"visible pixels reach the {'/'.join(measurement.edge_contact)} cell edge; "
                            "part of the Pet crosses into the next cell"
                        ),
                    }
                )

            frames.append(
                {
                    "path": label,
                    "state": state,
                    "column": column,
                    "empty": False,
                    "is_anchor": column == anchor_column,
                    "bbox": list(measurement.bbox),
                    "area": measurement.area,
                    "edge_contact": measurement.edge_contact,
                    "signals": signals,
                    "suspicion": 100 if hard_errors else suspicion_score(signals),
                    # The anchor is measured against itself, so its score is
                    # structurally 0 and says nothing about the artwork.
                    "suspicion_note": (
                        "anchor frame: compared against itself, so this score carries no information"
                        if column == anchor_column
                        else None
                    ),
                    "hard_errors": hard_errors,
                    # The agent fills this in after looking at the frame.
                    # `--verify-verdicts` fails while any entry is still null.
                    "agent_verdict": None,
                }
            )

    ranked = sorted(frames, key=lambda frame: -frame["suspicion"])
    payload = {
        "source": source,
        "bundle": str(grid.bundle),
        "atlas_digest": atlas_digest(atlas),
        "artwork_cells": ARTWORK_CELLS,
        "empty_cells": EMPTY_CELLS,
        "part_manifest": manifest.as_dicts(),
        "part_manifest_warning": manifest.warning,
        "safe_padding": safe_padding,
        "hard_errors": errors,
        "ok": not errors,
        "suspicion_order": [frame["path"] for frame in ranked],
        "frames": frames,
        "human_review": {
            "status": "pending",
            "question": "Approve the final audit by its digest, or name the frames to repair.",
        },
    }
    return AuditResult(payload=payload, cell_images=cell_images, anchor_images=anchor_images)


# --------------------------------------------------------------------------- #
# Review page
# --------------------------------------------------------------------------- #


def diff_overlay(cell: Image.Image, anchor: Image.Image) -> Image.Image:
    """Red where the frame has pixels the anchor lacks, blue where it lost them."""
    here_mask = alpha_mask(cell)
    there_mask = alpha_mask(anchor)
    out = bytearray(len(here_mask) * 4)
    for index, (here, there) in enumerate(zip(here_mask, there_mask)):
        if here == there:
            continue
        base = index * 4
        if here:
            out[base] = 230
        else:
            out[base + 2] = 230
        out[base + 3] = 200
    return Image.frombytes("RGBA", cell.size, bytes(out))


def strip_for(images: list[Image.Image]) -> Image.Image:
    strip = Image.new("RGBA", (CELL_WIDTH * max(1, len(images)), CELL_HEIGHT), (0, 0, 0, 0))
    for column, image in enumerate(images):
        strip.alpha_composite(image, (column * CELL_WIDTH, 0))
    return strip


def render_audit_html(result: AuditResult, grid: FrameGrid, output: Path, pet_name: str) -> None:
    payload = result.payload
    digest_short = payload["atlas_digest"][:12]
    by_path = {frame["path"]: frame for frame in payload["frames"]}

    if payload["part_manifest_warning"]:
        parts_block = (
            f'<p class="warn">No Part Manifest: {html.escape(payload["part_manifest_warning"])}. '
            "Audit every frame against <code>sources/canonical-base.png</code> instead, and add a "
            "<code>## Part Manifest</code> section to <code>character-bible.md</code>.</p>"
        )
        checklist_items = [
            "every part of the canonical base is present",
            "no part appears twice",
            "no part crosses the cell edge",
        ]
    else:
        rows = "".join(
            f"<tr><td>{html.escape(part['part'])}</td>"
            f"<td>{part['count_min']}–{part['count_max']}</td>"
            f"<td>{html.escape(part['side'])}</td>"
            f"<td>{html.escape(part['attachment'])}</td>"
            f"<td>{html.escape(part['notes'])}</td></tr>"
            for part in payload["part_manifest"]
        )
        parts_block = (
            "<table class='manifest'><thead><tr><th>Part</th><th>Count</th><th>Side</th>"
            f"<th>Attachment</th><th>Notes</th></tr></thead><tbody>{rows}</tbody></table>"
        )
        checklist_items = [f"{name} <span class='dim'>{count}</span>" for name, count in payload_checklist(payload)]

    checklist = "".join(f'<label><input type="checkbox"> {item}</label>' for item in checklist_items)

    hard_error_block = ""
    if payload["hard_errors"]:
        items = "".join(
            f"<li><code>{html.escape(error['path'])}</code> — {html.escape(error['message'])}</li>"
            for error in payload["hard_errors"]
        )
        hard_error_block = (
            f'<section class="errors"><h2>Hard errors ({len(payload["hard_errors"])})</h2><ul>{items}</ul></section>'
        )

    sections = []
    for state, _row, frame_count in ROW_SPECS:
        # One art strip and one overlay strip per state. Every card offsets into
        # the same two images, so the page carries 18 images instead of 114.
        labels = [grid.label(state, column) for column in range(frame_count)]
        cells = [result.cell_images.get(label) for label in labels]
        present = [cell for cell in cells if cell is not None]
        if not present:
            continue
        anchor = result.anchor_images.get(state)
        strip = strip_for(present)
        overlays = strip_for([diff_overlay(cell, anchor) for cell in present] if anchor is not None else [])
        slug = state.replace("-", "")

        cards = []
        for column, (label, cell) in enumerate(zip(labels, cells)):
            frame = by_path.get(label)
            if not frame or cell is None:
                continue
            signals = frame.get("signals", {})
            badge = "hard" if frame["hard_errors"] else ("high" if frame["suspicion"] >= SUSPICION_FLAG else "low")
            offset = f"background-position:-{column * CELL_WIDTH}px 0"
            signal_rows = "".join(
                f"<tr><td>{html.escape(key.replace('_', ' '))}</td><td>{html.escape(str(value))}</td></tr>"
                for key, value in signals.items()
            )
            cards.append(
                f"""
      <article class="frame {badge}">
        <header><b>{column:02d}</b>{' <span class="anchor">anchor</span>' if frame.get('is_anchor') else ''}
          <span class="score">{frame['suspicion']}</span></header>
        <div class="stage">
          <div class="art art-{slug}" style="{offset}"></div>
          <div class="ovl ovl-{slug}" style="{offset}"></div>
        </div>
        <code class="path">{html.escape(label)}</code>
        <div class="checks">{checklist}</div>
        <details><summary>signals</summary><table>{signal_rows}</table></details>
      </article>"""
            )

        sections.append(
            f"""
  <style>
    .art-{slug}, .loop-{slug} {{ background-image:url({data_uri(strip)}); }}
    .ovl-{slug} {{ background-image:url({data_uri(overlays)}); }}
    .loop-{slug} {{ animation:play-{slug} {len(present) * 0.12:.2f}s steps({len(present)}) infinite; }}
    @keyframes play-{slug} {{ from {{ background-position:0 0; }}
      to {{ background-position:-{CELL_WIDTH * len(present)}px 0; }} }}
  </style>
  <section class="state" id="{state}">
    <h2>{state} <span class="dim">{frame_count} frames</span></h2>
    <div class="loop loop-{slug}"></div>
    <div class="frames">{''.join(cards)}</div>
  </section>"""
        )

    flagged = sum(1 for frame in payload["frames"] if frame["suspicion"] >= SUSPICION_FLAG)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(pet_name)} — final anatomy audit</title>
<style>
:root {{ color-scheme: light dark; --bg:#faf9f7; --fg:#1c1c1c; --dim:#767676; --line:#e0ddd8;
        --hard:#c62828; --high:#b26a00; --low:#2e7d32; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15161a; --fg:#e9e7e3; --dim:#9a978f;
        --line:#2c2e34; --card:#1c1e23; }} }}
body {{ margin:0; padding:24px; background:var(--bg); color:var(--fg);
  font:14px/1.5 ui-sans-serif,-apple-system,system-ui,sans-serif; }}
h1 {{ font-size:20px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:0 0 12px; }}
.dim {{ color:var(--dim); font-weight:400; }}
.meta {{ color:var(--dim); margin-bottom:20px; }}
.meta code {{ user-select:all; }}
.warn {{ background:#fff3cd; color:#5c4400; padding:10px 12px; border-radius:6px; }}
@media (prefers-color-scheme: dark) {{ .warn {{ background:#3a2f00; color:#ffe08a; }} }}
table {{ border-collapse:collapse; font-size:12px; }}
th,td {{ border:1px solid var(--line); padding:4px 8px; text-align:left; }}
.manifest {{ margin-bottom:24px; }}
.errors {{ border-left:3px solid var(--hard); padding:8px 14px; margin:0 0 24px; }}
.errors code {{ color:var(--hard); }}
.state {{ margin-bottom:36px; padding-bottom:24px; border-bottom:1px solid var(--line); }}
.loop {{ width:{CELL_WIDTH}px; height:{CELL_HEIGHT}px; background-repeat:no-repeat; margin-bottom:16px;
  background-color:#fff; border:1px solid var(--line); border-radius:6px; }}
.frames {{ display:flex; flex-wrap:wrap; gap:14px; }}
.frame {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px;
  width:{CELL_WIDTH + 24}px; }}
.frame.hard {{ border-color:var(--hard); }} .frame.high {{ border-color:var(--high); }}
.frame header {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
.score {{ margin-left:auto; font-variant-numeric:tabular-nums; color:var(--dim); }}
.frame.hard .score {{ color:var(--hard); font-weight:700; }}
.frame.high .score {{ color:var(--high); font-weight:700; }}
.anchor {{ font-size:11px; color:var(--low); border:1px solid var(--low); border-radius:3px; padding:0 4px; }}
.stage {{ position:relative; width:{CELL_WIDTH}px; height:{CELL_HEIGHT}px; border-radius:4px; background:#fff;
  background-image:linear-gradient(45deg,#eee 25%,transparent 25%,transparent 75%,#eee 75%),
                   linear-gradient(45deg,#eee 25%,transparent 25%,transparent 75%,#eee 75%);
  background-size:16px 16px; background-position:0 0,8px 8px; }}
.stage .art, .stage .ovl {{ position:absolute; inset:0; background-repeat:no-repeat; }}
.ovl {{ opacity:0; transition:opacity .12s; }} .stage:hover .ovl {{ opacity:1; }}
.path {{ display:block; font-size:11px; color:var(--dim); margin:6px 0; }}
.checks {{ display:flex; flex-direction:column; gap:2px; font-size:12px; }}
details {{ margin-top:8px; font-size:12px; }} summary {{ cursor:pointer; color:var(--dim); }}
</style></head><body>
<h1>{html.escape(pet_name)} — final anatomy audit</h1>
<p class="meta">
  {ARTWORK_CELLS} artwork cells audited by eye · {EMPTY_CELLS} empty cells asserted by script ·
  source: {html.escape(payload['source'])}<br>
  atlas digest <code>{digest_short}</code> ·
  hard errors: <b>{len(payload['hard_errors'])}</b> ·
  flagged frames (suspicion ≥ {SUSPICION_FLAG}): <b>{flagged}</b> of {ARTWORK_CELLS}
</p>
<p class="meta">Hover a frame to see what it gained (red) or lost (blue) against its state's anchor frame.
Suspicion ranks attention only — a low score is not a pass. Approve by replying:
<code>I approve the final audit {digest_short} for {html.escape(pet_name)}.</code></p>
{parts_block}
{hard_error_block}
{''.join(sections)}
</body></html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def payload_checklist(payload: dict[str, Any]) -> list[tuple[str, str]]:
    items = []
    for part in payload["part_manifest"]:
        low, high = part["count_min"], part["count_max"]
        items.append((part["part"], f"{low}" if low == high else f"{low}-{high}"))
    return items


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def load_atlas(bundle: Path, mode: str, atlas_path: str | None) -> tuple[Image.Image, str]:
    if mode == "pre-export":
        return compose_atlas(bundle), "frames/ composed in memory"
    path = Path(atlas_path) if atlas_path else bundle / "final" / "spritesheet.webp"
    if not path.is_file():
        raise SystemExit(f"post-export audit needs an exported atlas; {path} is missing")
    with Image.open(path) as opened:
        atlas = opened.convert("RGBA")
    if atlas.size != (ATLAS_WIDTH, ATLAS_HEIGHT):
        raise SystemExit(f"{path} is {atlas.width}x{atlas.height}; expected {ATLAS_WIDTH}x{ATLAS_HEIGHT}")
    return atlas, str(path)


def compare_to_pre_export(payload: dict[str, Any], reference_path: Path) -> list[dict[str, Any]]:
    """Run two exists to catch encode damage. Silence means the file matches."""
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference["atlas_digest"] == payload["atlas_digest"]:
        return []
    mismatches: list[dict[str, Any]] = []
    before = {frame["path"]: frame for frame in reference["frames"]}
    for frame in payload["frames"]:
        earlier = before.get(frame["path"])
        if not earlier:
            continue
        if earlier.get("area") != frame.get("area") or earlier.get("bbox") != frame.get("bbox"):
            mismatches.append(
                {
                    "code": "encode_mismatch",
                    "path": frame["path"],
                    "message": (
                        f"exported pixels differ from the approved atlas: "
                        f"area {earlier.get('area')} → {frame.get('area')}, "
                        f"bbox {earlier.get('bbox')} → {frame.get('bbox')}"
                    ),
                }
            )
    if not mismatches:
        mismatches.append(
            {
                "code": "encode_mismatch",
                "path": "final/spritesheet",
                "message": (
                    "exported atlas digest differs from the approved atlas with no per-frame change; "
                    "re-export before delivery"
                ),
            }
        )
    return mismatches


def refit_state(grid: FrameGrid, state: str, safe_padding: int) -> tuple[float, list[Path]] | None:
    """Rescale a whole state by one shared factor so its widest pose fits.

    Cell bleed on frames that already exist is the most repairable defect there
    is, and the per-frame shift cannot touch it: a body wider than the safe box
    has no offset that puts it inside. What works is one factor derived from the
    UNION bounding box of the state, applied to every frame of that state. The
    frames stay in proportion to each other, so relative motion survives exactly.

    Per-frame rescaling would not. It re-fits each pose to itself, which makes a
    crouch come out the same size as a stretch -- the scale popping the QA rubric
    rejects, and the reason the generator derives one transform per run.

    Returns None when the state already fits, so a clean state is untouched.
    """
    paths = [path for path in grid.frame_paths(state) if path.is_file()]
    if not paths:
        return None

    union: tuple[int, int, int, int] | None = None
    for path in paths:
        with Image.open(path) as opened:
            box = alpha_bbox(opened.convert("RGBA"))
        if box is None:
            continue
        union = box if union is None else (
            min(union[0], box[0]), min(union[1], box[1]),
            max(union[2], box[2]), max(union[3], box[3]),
        )
    if union is None:
        return None

    left, top, right, bottom = union
    width = max(1, right - left)
    height = max(1, bottom - top)
    # Lanczos softens an edge by about a pixel and a soft pixel still counts as
    # visible, so the target box reserves one. Without it a refit lands the body
    # exactly on the safe-padding line and the re-audit reports the same bleed.
    room_x = CELL_WIDTH - 2 * safe_padding
    room_y = CELL_HEIGHT - 2 * safe_padding
    if width <= room_x and height <= room_y:
        return None

    factor = min((room_x - 2 * RESAMPLE_BLEED) / width, (room_y - 2 * RESAMPLE_BLEED) / height)
    centre_x = (left + right) / 2
    centre_y = (top + bottom) / 2
    offset_x = round(CELL_WIDTH / 2 - centre_x * factor)
    offset_y = round(CELL_HEIGHT / 2 - centre_y * factor)

    for path in paths:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        scaled = image.resize(
            (max(1, round(image.width * factor)), max(1, round(image.height * factor))),
            Image.LANCZOS,
        )
        cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
        cell.paste(scaled, (offset_x, offset_y))
        clear_transparent_rgb(cell).save(path)
    return factor, paths


def register_states(grid: FrameGrid, safe_padding: int) -> dict[str, str]:
    """Put every state on one anchor and one size. Free, and it moves no art.

    This is the repair for the two defects `geist_registration` describes: a
    body that changes size when the state changes, and a body that wanders while
    the state plays. Both are pure pixel arithmetic -- a shared rescale and a
    whole-pixel translation -- so neither costs a provider call, and neither
    invents a pixel that was not already drawn.

    Size is corrected towards the **median state**, not towards the canonical
    base's absolute size. The base is stored at provider resolution and the
    frames were fitted under whatever `--motion-headroom` that build used, so
    their absolute sizes are not comparable and chasing the base would rescale
    every state in a bundle that has nothing wrong with it. The median is what
    cross-state consistency actually means, and it leaves a healthy bundle
    untouched.

    Returns one note per changed frame, keyed the way `payload["frames"]` is, so
    a registered frame is not later mistaken for an unrepaired one.
    """
    canonical = grid.bundle / "sources" / "canonical-base.png"
    if not canonical.is_file():
        return {}
    with Image.open(canonical) as opened:
        target = registration.ruler(opened.convert("RGBA"), safe_padding)

    loaded: dict[str, list[tuple[Any, Image.Image]]] = {}
    ratios: dict[str, float] = {}
    for state, _row, _count in ROW_SPECS:
        frames = []
        for path in grid.frame_paths(state):
            if not path.is_file():
                continue
            with Image.open(path) as opened:
                frames.append((path, opened.convert("RGBA")))
        if not frames:
            continue
        anchors = [registration.measure(image) for _path, image in frames]
        anchors = [anchor for anchor in anchors if anchor is not None]
        if not anchors:
            continue
        loaded[state] = frames
        ratios[state] = registration.size_ratio(anchors, target)
    if not ratios:
        return {}

    middle = statistics.median(ratios.values())
    notes: dict[str, str] = {}
    for state, frames in loaded.items():
        applied: list[str] = []
        images = [image for _path, image in frames]

        factor = middle / ratios[state] if ratios[state] else 1.0
        if abs(factor - 1.0) > registration.SIZE_TOLERANCE:
            images = [_rescale_cell(image, factor) for image in images]
            applied.append(
                f"rescaled the whole {state} row by x{factor:.3f} onto the bundle's shared size"
            )

        images, moved = registration.register(images, state, target)
        if moved:
            budget = registration.budget_for(state)
            applied.append(
                f"registered {len(moved)} frame(s) onto the bundle anchor "
                f"(travel budget {budget[0]}x{budget[1]}px)"
            )
        if not applied:
            continue
        for (path, _old), image in zip(frames, images):
            clear_transparent_rgb(image).save(path)
            notes[grid.rel(path)] = "; ".join(applied)
    return notes


def _rescale_cell(image: Image.Image, factor: float) -> Image.Image:
    """Resize a finished cell about its centre, staying 192x208."""
    scaled = image.resize(
        (max(1, round(CELL_WIDTH * factor)), max(1, round(CELL_HEIGHT * factor))),
        Image.LANCZOS,
    )
    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    cell.paste(scaled, ((CELL_WIDTH - scaled.width) // 2, (CELL_HEIGHT - scaled.height) // 2))
    return cell


def run_repairs(grid: FrameGrid, payload: dict[str, Any], safe_padding: int) -> dict[str, Any]:
    """Repair what already exists; queue what would need new artwork."""
    log = load_repair_log(grid.bundle)
    deterministic: list[dict[str, Any]] = []
    generative: list[dict[str, Any]] = []
    flagged: list[dict[str, Any]] = []
    exhausted: list[str] = []

    # Cell bleed is a whole-state property, so it is settled before the per-frame
    # pass looks at anything. A state repaired here reaches that pass already
    # fitting, and carries the note so it is not mistaken for an unrepaired
    # frame and queued for paid regeneration.
    refitted: dict[str, str] = {}
    bleeding = {frame["state"] for frame in payload["frames"] if "cell_bleed" in frame["hard_errors"]}
    for state in sorted(bleeding):
        result = refit_state(grid, state, safe_padding)
        if result is None:
            continue
        factor, paths = result
        note = f"refit the whole {state} row by x{factor:.3f} from its union bounding box"
        for path in paths:
            refitted[grid.rel(path)] = note


    for frame in payload["frames"]:
        # A detached fragment is removable whatever its suspicion score, so it
        # gets repaired on its own evidence rather than on the ranking.
        has_fragment = frame.get("signals", {}).get("component_count", 1) > 1

        # Suspicion ranks which cells to LOOK at. It never buys new art.
        #
        # suspicion_score awards up to 40 points for bbox_delta alone, so a
        # `jumping` or directional frame crosses the flag by doing exactly what
        # its state is for. Sending that to generative repair spends provider
        # money on a correct frame and burns one of its two passes on the way.
        # Measured on the 2026-08-12 build: five frames queued for paid
        # regeneration on displacement alone, on an audit reporting `ok: true`
        # with zero hard errors.
        if not (frame["hard_errors"] or has_fragment):
            if frame["suspicion"] >= SUSPICION_FLAG:
                flagged.append(
                    {
                        "path": frame["path"],
                        "state": frame["state"],
                        "column": frame["column"],
                        "suspicion": frame["suspicion"],
                        "note": "ranked for a look; no hard error, so nothing is queued for redraw",
                    }
                )
            continue
        passes = log.get(frame["path"], 0)
        if passes >= MAX_REPAIR_PASSES:
            exhausted.append(frame["path"])
            continue

        frame_path = grid.frame_path(frame["state"], frame["column"])
        if frame_path is None or not frame_path.is_file():
            continue
        with Image.open(frame_path) as opened:
            image = opened.convert("RGBA")
        repaired, applied = deterministic_repair(image, measure_cell(image), safe_padding)
        if frame["path"] in refitted:
            applied.insert(0, refitted[frame["path"]])

        if applied:
            backup = back_up_frame(grid.bundle, frame_path, frame["state"], frame["column"], passes + 1)
            repaired.save(frame_path)
            log[frame["path"]] = passes + 1
            deterministic.append(
                {
                    "path": frame["path"],
                    "pass": passes + 1,
                    "applied": applied,
                    "backup": grid.rel(backup),
                }
            )
        else:
            # Queuing is the attempt. Counting it keeps the cap over generative
            # repair, which is the expensive half, instead of only over the free
            # deterministic half.
            log[frame["path"]] = passes + 1
            generative.append(
                {
                    "path": frame["path"],
                    "state": frame["state"],
                    "column": frame["column"],
                    "pass": passes + 1,
                    "passes_left": MAX_REPAIR_PASSES - (passes + 1),
                    "reason": frame["hard_errors"][0] if frame["hard_errors"] else "suspicion",
                    "suspicion": frame["suspicion"],
                }
            )

    # Registration goes last, and the order is the point. A refit rescales a row
    # and the per-frame pass deletes stray fragments -- both change where a body
    # measures. Registering first would anchor every frame to a bounding box that
    # a speck was still stretching, then leave it there.
    registered = register_states(grid, safe_padding)

    save_repair_log(grid.bundle, log)
    return {
        "deterministic": deterministic,
        "registered": [{"path": path, "applied": note} for path, note in sorted(registered.items())],
        "generative_repair_queue": generative,
        "flagged_for_review": flagged,
        "passes_exhausted": exhausted,
        "max_passes_per_frame": MAX_REPAIR_PASSES,
    }


def verify_verdicts(audit_path: Path) -> int:
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    missing = [frame["path"] for frame in payload["frames"] if frame.get("agent_verdict") is None]
    result = {
        "ok": not missing and not payload["hard_errors"],
        "artwork_cells": payload["artwork_cells"],
        "verdicts_recorded": payload["artwork_cells"] - len(missing),
        "missing_verdicts": missing,
        "hard_errors": payload["hard_errors"],
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--mode", choices=["pre-export", "post-export"], default="pre-export")
    parser.add_argument("--atlas", help="Atlas file for post-export mode; defaults to <bundle>/final/spritesheet.webp")
    parser.add_argument("--json-out", help="Defaults to <bundle>/qa/final-audit.json")
    parser.add_argument("--html-out", help="Defaults to <bundle>/qa/final-audit.html")
    parser.add_argument("--safe-padding", type=int, default=4)
    parser.add_argument("--repair", action="store_true", help="Apply deterministic repairs and queue the rest")
    parser.add_argument(
        "--verify-verdicts",
        action="store_true",
        help="Exit non-zero while any artwork cell still has a null agent_verdict",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    default_name = "final-audit" if args.mode == "pre-export" else "final-audit-post-export"
    audit_json = (
        Path(args.json_out).expanduser().resolve() if args.json_out else bundle / "qa" / f"{default_name}.json"
    )

    if args.verify_verdicts:
        raise SystemExit(verify_verdicts(audit_json))

    if args.mode == "post-export" and args.repair:
        raise SystemExit(
            "--repair edits source frames, so it belongs with --mode pre-export; "
            "a post-export audit reports encode damage instead"
        )

    grid = FrameGrid(bundle)
    manifest = read_manifest(bundle / "character-bible.md")
    atlas, source = load_atlas(bundle, args.mode, args.atlas)
    result = audit_atlas(atlas, grid, manifest=manifest, safe_padding=args.safe_padding, source=source)

    if args.mode == "post-export":
        reference = bundle / "qa" / "final-audit.json"
        if reference.is_file():
            mismatches = compare_to_pre_export(result.payload, reference)
            result.payload["encode_mismatches"] = mismatches
            result.payload["hard_errors"].extend(mismatches)
            result.payload["ok"] = not result.payload["hard_errors"]
        else:
            result.payload["encode_mismatches"] = []

    if args.repair:
        repairs = run_repairs(grid, result.payload, args.safe_padding)
        if repairs["deterministic"]:
            # Repairs rewrote frames, so the audit above describes pixels that no
            # longer exist. Re-audit, or the digest would bind an approval to art
            # the bundle no longer contains and export could never open the gate.
            atlas, source = load_atlas(bundle, args.mode, args.atlas)
            result = audit_atlas(atlas, grid, manifest=manifest, safe_padding=args.safe_padding, source=source)
        result.payload["repairs"] = repairs

    audit_json.parent.mkdir(parents=True, exist_ok=True)
    audit_json.write_text(json.dumps(result.payload, indent=2, default=str) + "\n", encoding="utf-8")

    html_out = Path(args.html_out).expanduser().resolve() if args.html_out else bundle / "qa" / f"{default_name}.html"
    render_audit_html(result, grid, html_out, bundle.stem)

    print(
        json.dumps(
            {
                "ok": result.payload["ok"],
                "mode": args.mode,
                "source": source,
                "atlas_digest": result.payload["atlas_digest"],
                "artwork_cells": ARTWORK_CELLS,
                "empty_cells": EMPTY_CELLS,
                "hard_errors": len(result.payload["hard_errors"]),
                "flagged_frames": sum(
                    1 for frame in result.payload["frames"] if frame["suspicion"] >= SUSPICION_FLAG
                ),
                "part_manifest_warning": manifest.warning,
                "audit_json": str(audit_json),
                "audit_html": str(html_out),
                "repairs": result.payload.get("repairs"),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if result.payload["ok"] else 1)


if __name__ == "__main__":
    main()
