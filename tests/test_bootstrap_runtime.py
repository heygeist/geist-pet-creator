from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PATH = ROOT / "skills" / "geist-pet-creator" / "scripts" / "bootstrap_runtime.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_runtime", BOOTSTRAP_PATH)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapRuntimeTests(unittest.TestCase):
    def test_missing_runtime_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"GEIST_PET_CREATOR_CACHE": directory}, clear=False):
                ready, detail = bootstrap.inspect_runtime()
                self.assertFalse(ready)
                self.assertIn("not installed", detail)

    def test_unowned_runtime_is_never_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"GEIST_PET_CREATOR_CACHE": directory}, clear=False):
                bootstrap.runtime_dir().mkdir(parents=True)
                with self.assertRaises(SystemExit) as raised:
                    bootstrap.remove(True)
                self.assertIn("unowned", str(raised.exception))
                self.assertTrue(bootstrap.runtime_dir().is_dir())

    def test_pillow_is_exactly_pinned(self) -> None:
        requirements = bootstrap.requirements_path().read_text(encoding="utf-8").strip()
        self.assertRegex(requirements, r"^Pillow==\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
