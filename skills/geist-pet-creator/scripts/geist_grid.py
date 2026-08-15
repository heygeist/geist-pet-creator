#!/usr/bin/env python3
"""The Geist atlas grid, and which file is which frame.

"Which file is frame N of sprite action S" had three answers across the scripts,
and they disagreed: one listed the directory, one globbed it, one built a name
from the column index. A finding could therefore name a file that did not exist.
FrameGrid is the one answer.
"""

from __future__ import annotations

from pathlib import Path

CELL_WIDTH = 192
CELL_HEIGHT = 208
COLUMNS = 8
ROWS = 9
ATLAS_WIDTH = COLUMNS * CELL_WIDTH
ATLAS_HEIGHT = ROWS * CELL_HEIGHT

# (sprite action, atlas row, frame count)
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

FRAME_COUNTS = {state: count for state, _row, count in ROW_SPECS}
STATE_ROWS = {state: row for state, row, _count in ROW_SPECS}

# 57 cells hold artwork and need eyes; 15 must be transparent and need a script.
ARTWORK_CELLS = sum(count for _state, _row, count in ROW_SPECS)
EMPTY_CELLS = COLUMNS * ROWS - ARTWORK_CELLS


def cell_box(row: int, column: int) -> tuple[int, int, int, int]:
    """Crop box of one atlas cell."""
    left = column * CELL_WIDTH
    top = row * CELL_HEIGHT
    return left, top, left + CELL_WIDTH, top + CELL_HEIGHT


class FrameGrid:
    """Maps sprite actions to the frame files that fill their atlas row."""

    def __init__(self, bundle: Path) -> None:
        self.bundle = bundle
        self.frames_root = bundle / "frames"

    def state_dir(self, state: str) -> Path:
        return self.frames_root / state

    def frame_paths(self, state: str) -> list[Path]:
        """Frame files in atlas order, whatever they are named.

        Truncated to the state's frame count, so a directory holding extra PNGs
        contributes the same frames every caller sees.
        """
        directory = self.state_dir(state)
        if not directory.is_dir():
            return []
        files = sorted(
            path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".png"
        )
        return files[: FRAME_COUNTS[state]]

    def all_frame_paths(self, state: str) -> list[Path]:
        """Every PNG in the state directory, untruncated, for count checks."""
        directory = self.state_dir(state)
        if not directory.is_dir():
            return []
        return sorted(
            path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".png"
        )

    def frame_path(self, state: str, index: int) -> Path | None:
        """The existing file at this position, or None when the row is short."""
        paths = self.frame_paths(state)
        return paths[index] if index < len(paths) else None

    def destination(self, state: str, index: int) -> Path:
        """Canonical path to write frame `index` of `state` to."""
        return self.state_dir(state) / f"{index:02d}.png"

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.bundle))
        except ValueError:
            return str(path)

    def label(self, state: str, index: int) -> str:
        """How a finding names this frame: the real file when one exists."""
        path = self.frame_path(state, index)
        return self.rel(path) if path else f"frames/{state}/{index:02d}.png"

    def artwork_cells(self):
        """Yield (state, row, column) for every cell that should hold artwork."""
        for state, row, frame_count in ROW_SPECS:
            for column in range(frame_count):
                yield state, row, column

    def empty_cells(self):
        """Yield (state, row, column) for every cell that must be transparent."""
        for state, row, frame_count in ROW_SPECS:
            for column in range(frame_count, COLUMNS):
                yield state, row, column
