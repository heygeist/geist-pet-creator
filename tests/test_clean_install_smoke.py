from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "geist-pet-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from export_geist_pet import atlas_digest, compose_atlas  # noqa: E402
from geist_grid import CELL_HEIGHT, CELL_WIDTH, FRAME_COUNTS  # noqa: E402


def make_frame(offset: int = 0) -> Image.Image:
    image = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((48 + offset, 38, 144 + offset, 166), fill=(255, 244, 226, 255), outline=(47, 184, 236, 255), width=8)
    draw.ellipse((78 + offset, 82, 84 + offset, 88), fill=(32, 32, 28, 255))
    draw.ellipse((108 + offset, 82, 114 + offset, 88), fill=(32, 32, 28, 255))
    draw.polygon(((96 + offset, 118), (86 + offset, 108), (78 + offset, 120), (96 + offset, 142), (114 + offset, 120), (106 + offset, 108)), fill=(255, 122, 51, 255))
    return image


class CleanInstallSmokeTests(unittest.TestCase):
    def test_validate_and_export_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "OriginalSmoke.pet"
            (bundle / "sources").mkdir(parents=True)
            (bundle / "qa").mkdir()
            (bundle / "pet.json").write_text(
                json.dumps({"id": "original-smoke", "displayName": "Original Smoke", "description": "Original CI fixture"}) + "\n",
                encoding="utf-8",
            )
            (bundle / "character-bible.md").write_text(
                "# Original Smoke\n\n## Part Manifest\n\n"
                "| Part | Count | Side | Attachment | Notes |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| body | 1 | center | root | Never duplicated |\n"
                "| heart | 1 | center | chest | Never duplicated |\n",
                encoding="utf-8",
            )
            base = make_frame()
            base.save(bundle / "sources" / "canonical-base.png")
            for state, count in FRAME_COUNTS.items():
                state_dir = bundle / "frames" / state
                state_dir.mkdir(parents=True)
                for index in range(count):
                    make_frame(index % 3 - 1).save(state_dir / f"{index:02d}.png")

            validation = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_source_bundle.py"), str(bundle)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

            digest = atlas_digest(compose_atlas(bundle))
            (bundle / "qa" / "approvals.json").write_text(
                json.dumps([{"approved_action": "final-audit", "decision": "approved", "atlas_digest": digest}]) + "\n",
                encoding="utf-8",
            )
            exported = subprocess.run(
                [sys.executable, str(SCRIPTS / "export_geist_pet.py"), str(bundle)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            webp = bundle / "final" / "spritesheet.webp"
            self.assertTrue(webp.is_file())
            with Image.open(webp) as atlas:
                self.assertEqual(atlas.size, (1536, 1872))


if __name__ == "__main__":
    unittest.main()
