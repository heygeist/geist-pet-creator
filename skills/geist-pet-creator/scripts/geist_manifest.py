#!/usr/bin/env python3
"""The Part Manifest: what the Pet is made of, how many of each, and what shape.

The audit counts frames against this list, and generation prompts quote it. Both
read it here, so a manifest the audit would reject can never reach a prompt.

Counting was the whole contract until 2026-08-13, and counting is necessary and
not sufficient. On `FuseSprout` the first `failed` draw replaced a connected face
glyph with separate eyes and a detached frown, and dropped the mouth tab across
all eight frames -- drift on the rank-2 identity cue, and $0.18 to redraw. **It
satisfied the manifest completely**: the manifest said `mouth shape | 1`, and the
drifted art had exactly one mouth. Counts go into the prompt and counts come back
out of the audit, so a part that keeps its count while changing its shape was
invisible to both.

The skill defines anatomy drift as a part missing, duplicated, or crossing the
cell line. Shape drift is a fourth kind. The optional `Shape` column is what a
prompt can steer with; `geist_pixels.component_count` is what an audit can check
without a human, and the two are deliberately separate -- a description the model
never has to satisfy is decoration, and a check with nothing to check against
only ever reports a number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECTION_PATTERN = re.compile(r"^##\s+Part Manifest\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
COUNT_PATTERN = re.compile(r"^\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*$")


# The historic column order, used when a table has no readable header row. New
# columns are found by NAME rather than by position, so adding one cannot shift
# the meaning of a bible written before it existed.
POSITIONAL_COLUMNS = ("part", "count", "side", "attachment", "notes")


@dataclass
class Part:
    name: str
    count_min: int
    count_max: int
    side: str
    attachment: str
    notes: str
    shape: str = ""

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
            "shape": self.shape,
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

    @property
    def shapes(self) -> list[Part]:
        """The parts whose shape is described, and therefore lockable."""
        return [part for part in self.parts if part.shape]

    def prompt_block(self) -> str:
        """The manifest as prompt text, so generation and audit ask for the same Pet.

        The shape sentences go in a block of their own, after the counts and
        introduced as a lock rather than as a list. A shape folded into the count
        line reads as a description of something already agreed; stated as its
        own instruction it reads as a requirement, and the whole point of the
        column is that a count the model already satisfies proved nothing.
        """
        if not self.parts:
            return ""
        lines = [
            f"- {part.name}: {part.count_label} ({part.side})" + (", never duplicated" if part.never_duplicated else "")
            for part in self.parts
        ]
        block = "\nThis Pet is made of exactly these parts:\n" + "\n".join(lines)

        described = self.shapes
        if described:
            block += (
                "\nDraw these parts in exactly this shape, in every frame, whatever the pose:\n"
                + "\n".join(f"- {part.name}: {part.shape}" for part in described)
            )
        return block

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
    columns: list[str] = list(POSITIONAL_COLUMNS)
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", ":", " "}:
            continue
        if cells[0].lower() == "part":
            columns = _header(cells)
            continue
        if not cells[0]:
            continue

        def column(name: str) -> str:
            index = columns.index(name) if name in columns else -1
            return cells[index] if 0 <= index < len(cells) else ""

        counts = COUNT_PATTERN.match(column("count"))
        if not counts:
            continue
        low = int(counts.group(1))
        high = int(counts.group(2)) if counts.group(2) else low
        parts.append(
            Part(
                name=cells[0],
                count_min=min(low, high),
                count_max=max(low, high),
                side=column("side"),
                attachment=column("attachment"),
                notes=column("notes"),
                shape=column("shape"),
            )
        )

    if not parts:
        return PartManifest([], "`## Part Manifest` section has no readable table rows")
    return PartManifest(parts, None)


def _header(cells: list[str]) -> list[str]:
    """Map a header row onto the column names this module knows.

    Read by name, never by position. A bible written before the `Shape` column
    existed has no header entry for it and simply reports no shapes; one that
    puts `Shape` between `Count` and `Side` is read correctly rather than having
    its sides silently become shapes. Anything unrecognised keeps its own header
    text, so it is skipped rather than mistaken for a column that matters.
    """
    known = ("part", "count", "side", "attachment", "notes", "shape")
    mapped: list[str] = []
    for cell in cells:
        lowered = cell.strip().lower()
        mapped.append(next((name for name in known if lowered.startswith(name)), lowered))
    return mapped
