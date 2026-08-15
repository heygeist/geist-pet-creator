#!/usr/bin/env python3
"""The Part Manifest: what the Pet is made of, and how many of each.

The audit counts frames against this list, and generation prompts quote it. Both
read it here, so a manifest the audit would reject can never reach a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECTION_PATTERN = re.compile(r"^##\s+Part Manifest\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
COUNT_PATTERN = re.compile(r"^\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*$")


@dataclass
class Part:
    name: str
    count_min: int
    count_max: int
    side: str
    attachment: str
    notes: str

    @property
    def never_duplicated(self) -> bool:
        return "never duplicated" in self.notes.lower()

    @property
    def count_label(self) -> str:
        return f"{self.count_min}" if self.count_min == self.count_max else f"{self.count_min}-{self.count_max}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "part": self.name,
            "count_min": self.count_min,
            "count_max": self.count_max,
            "side": self.side,
            "attachment": self.attachment,
            "notes": self.notes,
            "never_duplicated": self.never_duplicated,
        }


@dataclass
class PartManifest:
    parts: list[Part]
    warning: str | None

    def __bool__(self) -> bool:
        return bool(self.parts)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [part.as_dict() for part in self.parts]

    def prompt_block(self) -> str:
        """The manifest as prompt text, so generation and audit ask for the same Pet."""
        if not self.parts:
            return ""
        lines = [
            f"- {part.name}: {part.count_label} ({part.side})" + (", never duplicated" if part.never_duplicated else "")
            for part in self.parts
        ]
        return "\nThis Pet is made of exactly these parts:\n" + "\n".join(lines)

    def checklist(self) -> list[tuple[str, str]]:
        """Per-frame review items: (part name, expected count label)."""
        return [(part.name, part.count_label) for part in self.parts]


def read_manifest(bible_path: Path) -> PartManifest:
    """Read `## Part Manifest` from character-bible.md.

    A bundle without a manifest still audits, against the canonical base, so the
    warning travels with the result instead of stopping the run.
    """
    if not bible_path.is_file():
        return PartManifest([], "character-bible.md is missing")

    section = SECTION_PATTERN.search(bible_path.read_text(encoding="utf-8"))
    if not section:
        return PartManifest([], "character-bible.md has no `## Part Manifest` section")

    parts: list[Part] = []
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in {"part", ""} or set(cells[0]) <= {"-", ":", " "}:
            continue
        counts = COUNT_PATTERN.match(cells[1])
        if not counts:
            continue
        low = int(counts.group(1))
        high = int(counts.group(2)) if counts.group(2) else low
        parts.append(
            Part(
                name=cells[0],
                count_min=min(low, high),
                count_max=max(low, high),
                side=cells[2] if len(cells) > 2 else "",
                attachment=cells[3] if len(cells) > 3 else "",
                notes=cells[4] if len(cells) > 4 else "",
            )
        )

    if not parts:
        return PartManifest([], "`## Part Manifest` section has no readable table rows")
    return PartManifest(parts, None)
