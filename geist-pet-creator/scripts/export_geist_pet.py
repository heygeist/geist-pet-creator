#!/usr/bin/env python3
"""Export a validated Geist Pet source bundle to Geist-compatible assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from geist_grid import (
    ATLAS_HEIGHT,
    ATLAS_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    COLUMNS,
    ROW_SPECS,
    ROWS,
    FrameGrid,
    cell_box,
)
from geist_pixels import clear_transparent_rgb
from validate_source_bundle import validate_bundle


def load_metadata(bundle: Path) -> dict[str, Any]:
    metadata_path = bundle / "pet.json"
    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    pet_id = metadata.get("id")
    if not isinstance(pet_id, str) or not pet_id:
        raise SystemExit("pet.json must contain a non-empty string id")
    metadata.setdefault("displayName", pet_id)
    metadata.setdefault("description", "")
    return metadata


def compose_atlas(bundle: Path) -> Image.Image:
    atlas = Image.new("RGBA", (ATLAS_WIDTH, ATLAS_HEIGHT), (0, 0, 0, 0))
    grid = FrameGrid(bundle)
    for state, row, _frame_count in ROW_SPECS:
        for column, frame_path in enumerate(grid.frame_paths(state)):
            with Image.open(frame_path) as opened:
                frame = opened.convert("RGBA")
            if frame.size != (CELL_WIDTH, CELL_HEIGHT):
                raise SystemExit(
                    f"{frame_path} is {frame.width}x{frame.height}; expected {CELL_WIDTH}x{CELL_HEIGHT}"
                )
            atlas.alpha_composite(frame, (column * CELL_WIDTH, row * CELL_HEIGHT))
    return clear_transparent_rgb(atlas)


def atlas_digest(atlas: Image.Image) -> str:
    """Identify an exact set of pixels, so an approval cannot outlive the art."""
    return hashlib.sha256(atlas.convert("RGBA").tobytes()).hexdigest()


def audit_approval(bundle: Path, digest: str) -> dict[str, Any] | None:
    approvals_path = bundle / "qa" / "approvals.json"
    if not approvals_path.is_file():
        return None
    try:
        approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for entry in approvals if isinstance(approvals, list) else []:
        if (
            entry.get("approved_action") == "final-audit"
            and entry.get("decision") == "approved"
            and entry.get("atlas_digest") == digest
        ):
            return entry
    return None


def save_contact_sheet(atlas: Image.Image, output: Path) -> None:
    scale = 0.5
    cell_w = int(CELL_WIDTH * scale)
    cell_h = int(CELL_HEIGHT * scale)
    label_w = 118
    sheet = Image.new("RGBA", (label_w + COLUMNS * cell_w, ROWS * cell_h), (245, 245, 242, 255))
    draw = ImageDraw.Draw(sheet)
    for state, row, _frame_count in ROW_SPECS:
        for column in range(COLUMNS):
            cell = atlas.crop(cell_box(row, column))
            preview = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (255, 255, 255, 255))
            preview.alpha_composite(cell)
            preview = preview.resize((cell_w, cell_h), Image.Resampling.NEAREST)
            sheet.alpha_composite(preview, (label_w + column * cell_w, row * cell_h))
        # Keep labels plain and outside atlas output; default bitmap font is sufficient for QA.
        draw.text((8, row * cell_h + 8), state, fill=(40, 40, 40, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output)


def write_export_metadata(metadata: dict[str, Any], output_dir: Path, spritesheet_name: str) -> Path:
    exported = {
        "id": metadata["id"],
        "displayName": metadata.get("displayName", metadata["id"]),
        "description": metadata.get("description", ""),
        "spritesheetPath": spritesheet_name,
    }
    output_path = output_dir / "pet.json"
    output_path.write_text(json.dumps(exported, indent=2) + "\n", encoding="utf-8")
    return output_path


def install_export(output_dir: Path, metadata: dict[str, Any], spritesheet_name: str) -> Path:
    home = Path(os.environ.get("GEIST_HOME") or Path.home())
    pet_dir = home / ".geist" / "pets" / metadata["id"]
    pet_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_dir / "pet.json", pet_dir / "pet.json")
    shutil.copy2(output_dir / spritesheet_name, pet_dir / spritesheet_name)
    return pet_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--output-dir", help="Directory for exported assets; defaults to <bundle>/final")
    parser.add_argument("--png-only", action="store_true", help="Skip WebP output")
    parser.add_argument("--force", action="store_true", help="Export even when validation fails")
    parser.add_argument("--install", action="store_true", help="Install exported Pet into the local Geist catalog")
    parser.add_argument(
        "--skip-audit-gate",
        action="store_true",
        help="Export without an approved final anatomy audit; --force does not do this",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else bundle / "final"
    output_dir.mkdir(parents=True, exist_ok=True)

    validation = validate_bundle(bundle, safe_padding=4, fix_transparent_rgb=False)
    qa_dir = bundle / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    if not validation["ok"] and not args.force:
        raise SystemExit(f"validation failed; see {qa_dir / 'validation.json'}")

    metadata = load_metadata(bundle)
    atlas = compose_atlas(bundle)
    digest = atlas_digest(atlas)

    approval = audit_approval(bundle, digest)
    if approval is None and not args.skip_audit_gate:
        raise SystemExit(
            "no approved final anatomy audit for these exact frames.\n"
            f"  atlas digest: {digest[:12]}\n"
            "  run: python audit_spritesheet.py <bundle> --repair\n"
            "  then have the human approve qa/final-audit.html and record the approval in qa/approvals.json\n"
            "  with approved_action=final-audit, decision=approved, and this atlas_digest."
        )

    png_path = output_dir / "spritesheet.png"
    atlas.save(png_path)

    spritesheet_name = "spritesheet.png"
    webp_path = None
    if not args.png_only:
        webp_path = output_dir / "spritesheet.webp"
        atlas.save(webp_path, format="WEBP", lossless=True, quality=100, method=6, exact=True)
        spritesheet_name = "spritesheet.webp"

    metadata_path = write_export_metadata(metadata, output_dir, spritesheet_name)
    contact_sheet = qa_dir / "contact-sheet.png"
    save_contact_sheet(atlas, contact_sheet)

    installed_dir = None
    if args.install:
        installed_dir = install_export(output_dir, metadata, spritesheet_name)

    summary = {
        "ok": True,
        "bundle": str(bundle),
        "output_dir": str(output_dir),
        "pet_metadata": str(metadata_path),
        "spritesheet": str(output_dir / spritesheet_name),
        "png_spritesheet": str(png_path),
        "webp_spritesheet": str(webp_path) if webp_path else None,
        "validation": str(qa_dir / "validation.json"),
        "contact_sheet": str(contact_sheet),
        "atlas_digest": digest,
        "audit_approval": approval,
        "audit_gate_skipped": bool(args.skip_audit_gate and approval is None),
        "installed_dir": str(installed_dir) if installed_dir else None,
    }
    (qa_dir / "export-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
