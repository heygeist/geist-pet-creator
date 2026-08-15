#!/usr/bin/env python3
"""Fail closed on release-shape, licensing, and obvious secret mistakes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "geist-pet-creator"
REQUIRED = (
    ROOT / "LICENSE",
    ROOT / "ASSET_LICENSES.md",
    ROOT / "BRAND.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    SKILL / "SKILL.md",
    SKILL / "requirements.txt",
    SKILL / "scripts" / "bootstrap_runtime.py",
)
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt"}
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_TEXT = (
    "identity-cues-franchise-copy.jpg",
    "identity-cues-ranked.jpg",
    "identity-cues-crew.jpg",
    "identity-cues-labeled.jpg",
    "../measurements/",
    "assets/README.md",
)


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    if (ROOT / "install.sh").exists() or (ROOT / "geist-pet-creator").exists():
        errors.append("legacy root installer or legacy root skill directory is present")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\n"):
        errors.append("SKILL.md must start with YAML frontmatter")
    if "\nname: geist-pet-creator\n" not in skill_text:
        errors.append("SKILL.md name must be geist-pet-creator")
    if not re.search(r"\ndescription: .+\n---\n", skill_text):
        errors.append("SKILL.md needs a one-line description and closed frontmatter")

    assets = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (SKILL / "assets").glob("**/*")
        if path.is_file()
    )
    licenses = (ROOT / "ASSET_LICENSES.md").read_text(encoding="utf-8")
    for asset in assets:
        if asset not in licenses:
            errors.append(f"asset missing from ASSET_LICENSES.md: {asset}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET.search(text):
            errors.append(f"possible committed provider key: {path.relative_to(ROOT)}")
        if path.suffix.lower() == ".md":
            for raw_target in MARKDOWN_LINK.findall(text):
                target = raw_target.strip().strip("<>").split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    errors.append(
                        f"broken local Markdown link {raw_target!r}: {path.relative_to(ROOT)}"
                    )
        if path.is_relative_to(SKILL):
            for forbidden in FORBIDDEN_TEXT:
                if forbidden in text:
                    errors.append(f"forbidden stale reference {forbidden!r}: {path.relative_to(ROOT)}")
            if "/Users/" in text or "/home/" in text:
                errors.append(f"private absolute path in distributable skill: {path.relative_to(ROOT)}")

    if errors:
        print("repository checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"repository checks passed; {len(assets)} licensed asset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
