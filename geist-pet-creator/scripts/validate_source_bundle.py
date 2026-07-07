#!/usr/bin/env python3
"""Validate a Geist Pet source bundle made from alpha PNG frames."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

CELL_WIDTH = 192
CELL_HEIGHT = 208
ROW_SPECS = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
]


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


def png_files(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".png")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def alpha_bbox(rgba: Image.Image, alpha_threshold: int) -> tuple[int, int, int, int] | None:
    alpha = rgba.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > alpha_threshold else 0)
    return mask.getbbox()


def has_transparent_rgb_residue(rgba: Image.Image) -> int:
    count = 0
    data = rgba.tobytes()
    for index in range(0, len(data), 4):
        red = data[index]
        green = data[index + 1]
        blue = data[index + 2]
        alpha = data[index + 3]
        if alpha == 0 and (red or green or blue):
            count += 1
    return count


def clear_transparent_rgb(rgba: Image.Image) -> Image.Image:
    data = bytearray(rgba.tobytes())
    for index in range(0, len(data), 4):
        if data[index + 3] == 0:
            data[index] = 0
            data[index + 1] = 0
            data[index + 2] = 0
    return Image.frombytes("RGBA", rgba.size, bytes(data))


def is_green_or_cyan_fringe(red: int, green: int, blue: int) -> bool:
    green_fringe = green >= 180 and red <= 90 and green > blue * 1.25
    cyan_fringe = False
    return green_fringe or cyan_fringe


def edge_fringe_count(rgba: Image.Image, alpha_threshold: int) -> tuple[int, int]:
    width, height = rgba.size
    pixels = rgba.load()
    fringe = 0
    edge = 0
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha <= alpha_threshold:
                continue
            # Designed Pet outlines may be cyan/blue and fully opaque. Chroma residue
            # is usually semi-transparent antialiasing at the matte boundary.
            if alpha >= 245:
                continue
            boundary = True
            if not boundary:
                continue
            edge += 1
            if is_green_or_cyan_fringe(red, green, blue):
                fringe += 1
    return fringe, edge


def validate_frame(
    frame_path: Path,
    root: Path,
    findings: list[Finding],
    *,
    safe_padding: int,
    alpha_threshold: int,
    fix_transparent_rgb: bool,
) -> dict[str, Any]:
    frame_result: dict[str, Any] = {
        "path": rel(frame_path, root),
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
        findings.append(Finding("error", "unreadable_png", rel(frame_path, root), str(exc)))
        frame_result["ok"] = False
        return frame_result

    if not has_alpha:
        findings.append(
            Finding("error", "missing_alpha", rel(frame_path, root), "frame must be a PNG with alpha")
        )
        frame_result["ok"] = False

    if rgba.size != (CELL_WIDTH, CELL_HEIGHT):
        findings.append(
            Finding(
                "error",
                "wrong_dimensions",
                rel(frame_path, root),
                f"frame is {rgba.width}x{rgba.height}; expected {CELL_WIDTH}x{CELL_HEIGHT}",
            )
        )
        frame_result["ok"] = False

    bbox = alpha_bbox(rgba, alpha_threshold)
    frame_result["bbox"] = list(bbox) if bbox else None
    if bbox is None:
        findings.append(Finding("error", "empty_frame", rel(frame_path, root), "frame has no visible pixels"))
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
                    rel(frame_path, root),
                    f"visible pixels bbox {bbox} violates {safe_padding}px safe padding",
                )
            )
            frame_result["ok"] = False

    residue = has_transparent_rgb_residue(rgba)
    frame_result["transparent_rgb_residue_pixels"] = residue
    if residue:
        severity = "warning" if fix_transparent_rgb else "error"
        findings.append(
            Finding(
                severity,
                "transparent_rgb_residue",
                rel(frame_path, root),
                f"{residue} fully transparent pixels retain nonzero RGB values",
            )
        )
        if not fix_transparent_rgb:
            frame_result["ok"] = False
        else:
            clear_transparent_rgb(rgba).save(frame_path)

    fringe, edge = edge_fringe_count(rgba, alpha_threshold)
    frame_result["edge_fringe_pixels"] = fringe
    frame_result["edge_pixels"] = edge
    if fringe >= 8 and edge and fringe / edge >= 0.03:
        findings.append(
            Finding(
                "error",
                "green_cyan_fringe",
                rel(frame_path, root),
                f"{fringe}/{edge} boundary pixels look like green/cyan fringe",
            )
        )
        frame_result["ok"] = False

    return frame_result


def validate_bundle(
    bundle: Path,
    *,
    safe_padding: int,
    alpha_threshold: int,
    fix_transparent_rgb: bool,
) -> dict[str, Any]:
    findings: list[Finding] = []
    frames_root = bundle / "frames"
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
    if not frames_root.is_dir():
        findings.append(Finding("error", "missing_frames_root", "frames", "source bundle needs frames/"))
    else:
        for state, _row, frame_count in ROW_SPECS:
            state_dir = frames_root / state
            state_key = rel(state_dir, bundle)
            if not state_dir.is_dir():
                findings.append(Finding("error", "missing_state_dir", state_key, f"missing {state} frames"))
                continue
            files = png_files(state_dir)
            if len(files) != frame_count:
                findings.append(
                    Finding(
                        "error",
                        "wrong_frame_count",
                        state_key,
                        f"{state} needs exactly {frame_count} PNG frames; found {len(files)}",
                    )
                )
            frame_results[state] = [
                validate_frame(
                    frame,
                    bundle,
                    findings,
                    safe_padding=safe_padding,
                    alpha_threshold=alpha_threshold,
                    fix_transparent_rgb=fix_transparent_rgb,
                )
                for frame in files[:frame_count]
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
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument(
        "--fix-transparent-rgb",
        action="store_true",
        help="Zero RGB channels for fully transparent pixels in-place",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    result = validate_bundle(
        bundle,
        safe_padding=args.safe_padding,
        alpha_threshold=args.alpha_threshold,
        fix_transparent_rgb=args.fix_transparent_rgb,
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
