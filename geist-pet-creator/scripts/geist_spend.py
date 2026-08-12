#!/usr/bin/env python3
"""One line per provider call, written the moment the cost is known.

Per-call cost already lands in every candidate packet. A packet only exists once
a run finishes writing one, though, and the spend worth seeing most is the spend
that produced no artifact: a run killed at a ceiling, a `--verify-model` probe, a
chroma-key retry that preceded a crash. So the ledger is appended when the
provider answers, not when the packet lands.

Two files, two jobs, two failure policies:

  <bundle>/qa/spend.jsonl                   authoritative; a failed write is fatal
  ${GEIST_HOME:-$HOME}/.geist/spend.jsonl   convenience; a failed write warns

The split follows what is recoverable. A lost bundle line is gone. A lost home
line can be rebuilt by walking bundle ledgers, so losing it must not kill a build
that is forty frames in.

Both files carry the same line shape, so one reader serves either.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_FILENAME = "spend.jsonl"
SCHEMA = 1

# A single write() of a single short line is what makes concurrent appends safe,
# and this skill runs candidate subagents in parallel. Lines are held under this
# bound so that stays true: a line over the bound sheds its optional fields
# rather than its atomicity.
MAX_LINE_BYTES = 4096

KIND_DRAW = "draw"
KIND_VERIFY = "verify-model"
KINDS = (KIND_DRAW, KIND_VERIFY)

MODE_AUTO = "auto"
MODE_SUPERVISED = "supervised"
MODES = (MODE_AUTO, MODE_SUPERVISED)

# Shed in this order when a line runs long. Everything left is what a rollup
# needs to be arithmetic rather than guesswork.
SHEDDABLE = ("note", "endpoint", "candidate_id", "frame")


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bundle_ledger(bundle: Path | str) -> Path:
    return Path(bundle) / "qa" / LEDGER_FILENAME


def home_ledger() -> Path:
    """Resolved exactly the way export_geist_pet.py resolves an install target,
    so one GEIST_HOME moves the Pets and their receipts together."""
    home = Path(os.environ.get("GEIST_HOME") or Path.home())
    return home / ".geist" / LEDGER_FILENAME


def pet_id_for(bundle: Path | str) -> str:
    """`pet.json`'s id is the join key across both ledgers, because a bundle path
    changes when someone renames or copies a directory and the id does not.

    Falls back to the directory name: a ledger line is worth more than the
    exactness of its key, and spend recorded before `pet.json` exists still
    happened.
    """
    bundle = Path(bundle)
    try:
        raw = json.loads((bundle / "pet.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return bundle.name
    pet_id = raw.get("id") if isinstance(raw, dict) else None
    return pet_id if isinstance(pet_id, str) and pet_id else bundle.name


def build_record(
    *,
    kind: str,
    action: str | None,
    model: str,
    mode: str | None,
    cost_usd: float | None,
    images: int = 1,
    pet_id: str | None = None,
    bundle: Path | str | None = None,
    provider: str = "openrouter",
    **optional: Any,
) -> dict[str, Any]:
    """Build one ledger line.

    `cost_usd` of None means unpriced rather than free -- built-in image
    generation reports no price, and inventing one for a file that reads like a
    receipt would be worse than admitting the gap. `priced` makes the difference
    machine-readable so a rollup never sums a guess.
    """
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "at": now_stamp(),
        "pet_id": pet_id,
        "bundle": str(Path(bundle).resolve()) if bundle is not None else None,
        "kind": kind,
        "action": action,
        "mode": mode,
        "provider": provider,
        "model": model,
        "images": images,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        "priced": cost_usd is not None,
    }
    record.update({key: value for key, value in optional.items() if value is not None})
    return record


def _serialize(record: dict[str, Any]) -> bytes:
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
        return (line + "\n").encode("utf-8")
    trimmed = dict(record)
    for field in SHEDDABLE:
        trimmed.pop(field, None)
        line = json.dumps(trimmed, sort_keys=True, separators=(",", ":"))
        if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
            break
    return (line + "\n").encode("utf-8")


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _serialize(record)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(handle, payload)
    finally:
        os.close(handle)


def write(record: dict[str, Any], bundle: Path | str | None = None) -> list[str]:
    """Append to both ledgers. Returns warnings; raises only on the bundle write.

    A bundle without a writable `qa/` cannot record what it spent, and a Pet that
    cannot account for its own cost is a defect. The home ledger is a view over
    those lines, so its failure is reported and the run continues.
    """
    if bundle is not None:
        _append(bundle_ledger(bundle), record)

    warnings: list[str] = []
    target = home_ledger()
    try:
        _append(target, record)
    except OSError as error:
        warnings.append(
            f"home ledger not written ({target}): {error}. "
            "Rebuild it from bundle ledgers with spend_report.py when the path is writable."
        )
    return warnings


class SpendLedger:
    """The context one run shares across its calls.

    Held by `SpendGuard`, which already sees every cost including retries and
    chroma-key fallbacks, so a second call for the same frame is a second line.
    """

    def __init__(
        self,
        *,
        model: str,
        mode: str | None,
        action: str | None = None,
        bundle: Path | str | None = None,
        pet_id: str | None = None,
        candidate_id: str | None = None,
        kind: str = KIND_DRAW,
        provider: str = "openrouter",
        endpoint: str | None = None,
    ) -> None:
        self.bundle = Path(bundle).resolve() if bundle is not None else None
        self.pet_id = pet_id if pet_id is not None else (pet_id_for(self.bundle) if self.bundle else None)
        self.action = action
        self.model = model
        self.mode = mode
        self.kind = kind
        self.provider = provider
        self.endpoint = endpoint
        self.candidate_id: str | None = candidate_id
        # Set by a frame loop so a line can name the frame it paid for. The guard
        # sees the cost, not the loop counter, so the loop leaves it here.
        self.frame: int | None = None
        self.lines = 0
        self.warnings: list[str] = []

    def record(self, cost_usd: float | None, *, images: int = 1, **optional: Any) -> None:
        optional.setdefault("frame", self.frame)
        record = build_record(
            kind=self.kind,
            action=self.action,
            model=self.model,
            mode=self.mode,
            cost_usd=cost_usd,
            images=images,
            pet_id=self.pet_id,
            bundle=self.bundle,
            provider=self.provider,
            candidate_id=self.candidate_id,
            endpoint=self.endpoint,
            **optional,
        )
        for warning in write(record, self.bundle):
            if warning not in self.warnings:
                self.warnings.append(warning)
        self.lines += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_ledger": str(bundle_ledger(self.bundle)) if self.bundle else None,
            "home_ledger": str(home_ledger()),
            "lines_written": self.lines,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def read_ledger(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Return (records, malformed_line_count).

    A malformed line is counted rather than raised on. Two processes appending is
    safe by construction, but a ledger can also be edited by hand, and one bad
    line must not hide the hundred good ones above it.
    """
    records: list[dict[str, Any]] = []
    malformed = 0
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return records, malformed
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            malformed += 1
    return records, malformed


def resolve_targets(paths: list[str]) -> list[Path]:
    """Accept what a person would actually type: a bundle, a ledger, a directory.

    A directory that is not itself a bundle is walked one level for `*.pet`, which
    is how a workspace of Pets is summed without naming each one.
    """
    resolved: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_file():
            resolved.append(path)
            continue
        if not path.is_dir():
            continue
        candidate = bundle_ledger(path)
        if candidate.is_file():
            resolved.append(candidate)
            continue
        resolved.extend(
            sorted(
                child / "qa" / LEDGER_FILENAME
                for child in path.iterdir()
                if child.is_dir() and (child / "qa" / LEDGER_FILENAME).is_file()
            )
        )
    return resolved


def rollup(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate per Pet, keyed on `pet_id`.

    Unpriced images are counted separately rather than folded in as zero: a
    built-in-mode build spent effort the cost column cannot describe, and a
    silent zero would read as free.
    """
    pets: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record.get("pet_id") or "(unknown)"
        entry = pets.setdefault(
            key,
            {
                "pet_id": key,
                "calls": 0,
                "images": 0,
                "cost_usd": 0.0,
                "unpriced_images": 0,
                "actions": {},
                "models": set(),
                "bundles": set(),
                "first": None,
                "last": None,
            },
        )
        images = record.get("images") or 0
        cost = record.get("cost_usd")
        entry["calls"] += 1
        entry["images"] += images
        if record.get("priced") and isinstance(cost, (int, float)):
            entry["cost_usd"] += float(cost)
        else:
            entry["unpriced_images"] += images

        action = record.get("action") or record.get("kind") or "(none)"
        by_action = entry["actions"].setdefault(action, {"calls": 0, "images": 0, "cost_usd": 0.0})
        by_action["calls"] += 1
        by_action["images"] += images
        if record.get("priced") and isinstance(cost, (int, float)):
            by_action["cost_usd"] += float(cost)

        if record.get("model"):
            entry["models"].add(record["model"])
        if record.get("bundle"):
            entry["bundles"].add(record["bundle"])
        stamp = record.get("at")
        if isinstance(stamp, str):
            entry["first"] = stamp if entry["first"] is None else min(entry["first"], stamp)
            entry["last"] = stamp if entry["last"] is None else max(entry["last"], stamp)
    return pets
