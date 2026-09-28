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


def desaturate_fringe(rgba: Image.Image, alpha_threshold: int, detect_cyan: bool = False) -> int:
    """Neutralise chroma spill on boundary pixels. Returns how many were changed.

    Deterministic, and it preserves every visible shape: only the hue of a
    semi-transparent edge pixel moves, pulled to that pixel's own luminance so
    the outline keeps its softness and its position.

    It reuses `is_green_fringe`, `boundary_mask` and the two thresholds the gate
    reads, rather than re-deriving them. A hand-rolled version of this cleanup
    written against `alpha > 16` silently cleaned nothing on a real bundle,
    because the spill sat at alpha 9-16 — inside `ALPHA_THRESHOLD = 8`'s visible
    band and below `OPAQUE_THRESHOLD`, which is exactly the population the gate
    counts. A cleanup and its gate that read different constants cannot agree.
    """
    boundary = boundary_mask(rgba, alpha_threshold).tobytes()
    pixels = bytearray(rgba.tobytes())
    cleaned = 0
    for index, on_boundary in enumerate(boundary):
        if not on_boundary:
            continue
        base = index * 4
        if pixels[base + 3] >= OPAQUE_THRESHOLD:
            continue
        red, green, blue = pixels[base], pixels[base + 1], pixels[base + 2]
        if not (is_green_fringe(red, green, blue) or (detect_cyan and is_cyan_fringe(red, green, blue))):
            continue
        grey = (red * 299 + green * 587 + blue * 114) // 1000
        pixels[base] = pixels[base + 1] = pixels[base + 2] = grey
        cleaned += 1
    if cleaned:
        rgba.frombytes(bytes(pixels))
    return cleaned


def validate_frame(
    frame_path: Path,
    grid: FrameGrid,
    findings: list[Finding],
    *,
    safe_padding: int,
    alpha_threshold: int,
    fix_transparent_rgb: bool,
    fix_fringe: bool,
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
        if fix_fringe:
            cleaned = desaturate_fringe(rgba, alpha_threshold, detect_cyan)
            rgba.save(frame_path)
            frame_result["fringe_pixels_cleaned"] = cleaned
            findings.append(
                Finding(
                    "warning",
                    "green_cyan_fringe",
                    label,
                    f"{fringe}/{edge} boundary pixels looked like chroma fringe; "
                    f"desaturated {cleaned}",
                )
            )
        else:
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


# A pet.json description is the Pet's signature in words: silhouette and crown
# cue, palette and face, prop and attachments, motion personality. A generic
# one-liner that could fit any Geist fails, because the catalog copy is the only
# thing that names the Pet where the spritesheet is not shown.
DESCRIPTION_MIN_WORDS = 40
DESCRIPTION_MIN_CHARS = 200


def check_metadata_description(metadata_path: Path) -> list[Finding]:
    """The description gate: detailed signature copy, never a generic one-liner."""
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return [Finding("error", "unreadable_pet_metadata", "pet.json", f"pet.json cannot be read: {error}")]
    description = metadata.get("description", "")
    if not isinstance(description, str) or not description.strip():
        return [
            Finding(
                "error",
                "missing_description",
                "pet.json",
                "pet.json needs a detailed description of this Pet's signature: silhouette and "
                "crown cue, palette and face, prop, and motion personality. See contract.md § Pet Metadata.",
            )
        ]
    words = len(description.split())
    chars = len(description.strip())
    if words < DESCRIPTION_MIN_WORDS or chars < DESCRIPTION_MIN_CHARS:
        return [
            Finding(
                "error",
                "generic_description",
                "pet.json",
                f"description is generic ({words} words, {chars} chars; needs at least "
                f"{DESCRIPTION_MIN_WORDS} words and {DESCRIPTION_MIN_CHARS} chars). Rewrite it from the "
                "approved canonical base: crown cue, palette, face, prop, and how it idles, "
                "greets, works, and fails. See contract.md § Pet Metadata.",
            )
        ]
    return []


def validate_bundle(
    bundle: Path,
    *,
    safe_padding: int,
    alpha_threshold: int = ALPHA_THRESHOLD,
    fix_transparent_rgb: bool = False,
    fix_fringe: bool = False,
    detect_cyan: bool = False,
) -> dict[str, Any]:
    findings: list[Finding] = []
    grid = FrameGrid(bundle)
    frame_results: dict[str, list[dict[str, Any]]] = {}

    if not (bundle / "pet.json").is_file():
        findings.append(Finding("error", "missing_pet_metadata", "pet.json", "source bundle needs pet.json"))
    else:
        findings.extend(check_metadata_description(bundle / "pet.json"))
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
                    fix_fringe=fix_fringe,
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
        "--fix-green-fringe",
        action="store_true",
        help="Desaturate chroma spill on boundary pixels in-place. Deterministic and "
             "shape-preserving: it moves the hue of semi-transparent edge pixels to their own "
             "luminance and touches nothing else, so it needs no approval. Every chroma-path "
             "frame carries this spill, and without the fix the only cure was a redraw.",
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
        fix_fringe=args.fix_green_fringe,
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
