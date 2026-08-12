#!/usr/bin/env python3
"""Validate a Geist Pet source bundle made from alpha PNG frames."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from geist_grid import CELL_HEIGHT, CELL_WIDTH, FRAME_COUNTS, ROW_SPECS, FrameGrid
from geist_pixels import (
    ALPHA_THRESHOLD,
    OPAQUE_THRESHOLD,
    alpha_bbox,
    boundary_mask,
    clear_transparent_rgb,
    transparent_rgb_residue,
)

# Chroma residue is a semi-transparent green or cyan halo at the matte boundary.
# A designed Pet outline may be any colour, but it is solid, so opacity excludes it.
FRINGE_MIN_PIXELS = 8
FRINGE_MIN_RATIO = 0.03


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def is_green_fringe(red: int, green: int, blue: int) -> bool:
    """Green matte residue: bright green that dominates both other channels."""
    return green >= 180 and red <= 90 and green > blue * 1.25


def is_cyan_fringe(red: int, green: int, blue: int) -> bool:
    """Near-pure cyan matte residue.

    Deliberately narrow. Geist Pets are frequently drawn with blue or teal
    outlines, and the antialiased edge of such an outline reads as cyan-ish —
    rgb(0,128,192) is a real measured example. Only near-pure cyan with green
    and blue in balance is matte residue, so this stays opt-in per bundle.
    """
    return red <= 60 and green >= 200 and blue >= 200 and abs(green - blue) <= 40


def fringe_counts(rgba: Image.Image, alpha_threshold: int, detect_cyan: bool = False) -> tuple[int, int]:
    """Count chroma fringe among genuine boundary pixels.

    Boundary means visible and touching a non-visible pixel. Counting every
    semi-transparent pixel instead inflates the denominator and hides fringe.
    """
    boundary = boundary_mask(rgba, alpha_threshold).tobytes()
    pixels = rgba.tobytes()

    edge = 0
    fringe = 0
    for index, on_boundary in enumerate(boundary):
        if not on_boundary:
            continue
        base = index * 4
        if pixels[base + 3] >= OPAQUE_THRESHOLD:
            continue
        edge += 1
        red, green, blue = pixels[base], pixels[base + 1], pixels[base + 2]
        if is_green_fringe(red, green, blue) or (detect_cyan and is_cyan_fringe(red, green, blue)):
            fringe += 1
    return fringe, edge


def validate_frame(
    frame_path: Path,
    grid: FrameGrid,
    findings: list[Finding],
    *,
    safe_padding: int,
    alpha_threshold: int,
    fix_transparent_rgb: bool,
    detect_cyan: bool,
) -> dict[str, Any]:
    label = grid.rel(frame_path)
    frame_result: dict[str, Any] = {
        "path": label,
        "ok": True,
        "bbox": None,
        "transparent_rgb_residue_pixels": 0,
        "edge_fringe_pixels": 0,
        "edge_pixels": 0,
    }
    try:
        with Image.open(frame_path) as opened:
            has_alpha = opened.mode in {"RGBA", "LA"} or "transparency" in opened.info
            rgba = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        findings.append(Finding("error", "unreadable_png", label, str(exc)))
        frame_result["ok"] = False
        return frame_result

    if not has_alpha:
        findings.append(Finding("error", "missing_alpha", label, "frame must be a PNG with alpha"))
        frame_result["ok"] = False

    if rgba.size != (CELL_WIDTH, CELL_HEIGHT):
        findings.append(
            Finding(
                "error",
                "wrong_dimensions",
                label,
                f"frame is {rgba.width}x{rgba.height}; expected {CELL_WIDTH}x{CELL_HEIGHT}",
            )
        )
        frame_result["ok"] = False

    bbox = alpha_bbox(rgba, alpha_threshold)
    frame_result["bbox"] = list(bbox) if bbox else None
    if bbox is None:
        findings.append(Finding("error", "empty_frame", label, "frame has no visible pixels"))
        frame_result["ok"] = False
    else:
        left, top, right, bottom = bbox
        if (
            left < safe_padding
            or top < safe_padding
            or right > CELL_WIDTH - safe_padding
            or bottom > CELL_HEIGHT - safe_padding
        ):
            findings.append(
                Finding(
                    "error",
                    "unsafe_bounds",
                    label,
                    f"visible pixels bbox {bbox} violates {safe_padding}px safe padding",
                )
            )
            frame_result["ok"] = False

    residue = transparent_rgb_residue(rgba)
    frame_result["transparent_rgb_residue_pixels"] = residue
    if residue:
        findings.append(
            Finding(
                "warning" if fix_transparent_rgb else "error",
                "transparent_rgb_residue",
                label,
                f"{residue} fully transparent pixels retain nonzero RGB values",
            )
        )
        if fix_transparent_rgb:
            clear_transparent_rgb(rgba).save(frame_path)
        else:
            frame_result["ok"] = False

    fringe, edge = fringe_counts(rgba, alpha_threshold, detect_cyan)
    frame_result["edge_fringe_pixels"] = fringe
    frame_result["edge_pixels"] = edge
    if fringe >= FRINGE_MIN_PIXELS and edge and fringe / edge >= FRINGE_MIN_RATIO:
        findings.append(
            Finding(
                "error",
                "green_cyan_fringe",
                label,
                f"{fringe}/{edge} boundary pixels look like chroma fringe",
            )
        )
        frame_result["ok"] = False

    return frame_result


def validate_bundle(
    bundle: Path,
    *,
    safe_padding: int,
    alpha_threshold: int = ALPHA_THRESHOLD,
    fix_transparent_rgb: bool = False,
    detect_cyan: bool = False,
) -> dict[str, Any]:
    findings: list[Finding] = []
    grid = FrameGrid(bundle)
    frame_results: dict[str, list[dict[str, Any]]] = {}

    if not (bundle / "pet.json").is_file():
        findings.append(Finding("error", "missing_pet_metadata", "pet.json", "source bundle needs pet.json"))
    if not (bundle / "character-bible.md").is_file():
        findings.append(
            Finding("warning", "missing_character_bible", "character-bible.md", "identity QA needs a character bible")
        )
    if not (bundle / "sources" / "canonical-base.png").is_file():
        findings.append(
            Finding(
                "warning",
                "missing_canonical_base",
                "sources/canonical-base.png",
                "frame generation and repair should use a canonical base image",
            )
        )
    if not grid.frames_root.is_dir():
        findings.append(Finding("error", "missing_frames_root", "frames", "source bundle needs frames/"))
    else:
        for state, _row, frame_count in ROW_SPECS:
            state_key = grid.rel(grid.state_dir(state))
            if not grid.state_dir(state).is_dir():
                findings.append(Finding("error", "missing_state_dir", state_key, f"missing {state} frames"))
                continue
            present = grid.all_frame_paths(state)
            if len(present) != frame_count:
                findings.append(
                    Finding(
                        "error",
                        "wrong_frame_count",
                        state_key,
                        f"{state} needs exactly {frame_count} PNG frames; found {len(present)}",
                    )
                )
            frame_results[state] = [
                validate_frame(
                    frame,
                    grid,
                    findings,
                    safe_padding=safe_padding,
                    alpha_threshold=alpha_threshold,
                    fix_transparent_rgb=fix_transparent_rgb,
                    detect_cyan=detect_cyan,
                )
                for frame in grid.frame_paths(state)
            ]

    errors = [finding.as_dict() for finding in findings if finding.severity == "error"]
    warnings = [finding.as_dict() for finding in findings if finding.severity == "warning"]
    return {
        "ok": not errors,
        "bundle": str(bundle),
        "contract": {
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "states": [
                {"state": state, "row": row, "frame_count": frame_count}
                for state, row, frame_count in ROW_SPECS
            ],
        },
        "errors": errors,
        "warnings": warnings,
        "frames": frame_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--json-out", help="Write validation JSON to this path")
    parser.add_argument("--safe-padding", type=int, default=4)
    parser.add_argument("--alpha-threshold", type=int, default=ALPHA_THRESHOLD)
    parser.add_argument(
        "--fix-transparent-rgb",
        action="store_true",
        help="Zero RGB channels for fully transparent pixels in-place",
    )
    parser.add_argument(
        "--detect-cyan-fringe",
        action="store_true",
        help="Also flag near-pure cyan matte residue; off by default because Pet outlines are often blue or teal",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    result = validate_bundle(
        bundle,
        safe_padding=args.safe_padding,
        alpha_threshold=args.alpha_threshold,
        fix_transparent_rgb=args.fix_transparent_rgb,
        detect_cyan=args.detect_cyan_fringe,
    )
    output = json.dumps(result, indent=2)
    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()


# Frame counts stay importable for callers that only need the contract.
__all__ = ["FRAME_COUNTS", "ROW_SPECS", "CELL_WIDTH", "CELL_HEIGHT", "validate_bundle"]
