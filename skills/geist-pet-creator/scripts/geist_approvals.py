#!/usr/bin/env python3
"""`qa/approvals.json`: the record of what a human agreed to.

This module exists because the file had two shapes and one reader. SKILL.md said
to record an approval "with candidate id, approved file path, target destination,
approver note, and timestamp". `export_geist_pet.audit_approval` requires a
**top-level JSON array** whose entries carry `approved_action` and
`decision: "approved"` -- two fields the documented list never mentions. An agent
following the prose wrote `{"approvals": [...]}` and lost two export attempts to
it on 2026-08-12; a second build hit the same wall on 2026-08-13.

The reader's error message was excellent and diagnosed it immediately. That is
not a fix. A schema whose only definition is a reader is a schema every writer
has to reverse-engineer, and the reader is not there when the writing happens.

So the writer lives here, beside the reader, and both sides import it. The field
names are `references/contract.md`'s, unchanged -- this module exists to reduce
the number of shapes the file has, so it does not get to add a third:

    python geist_approvals.py PetName.pet --action final-audit \\
        --atlas-digest <digest> --note "what the human said"

    python geist_approvals.py PetName.pet --action waiting \\
        --candidate-id waiting-b --approved-for frames/waiting/ \\
        --source qa/waiting-review.html --decided-by human --note "..."

An approval is **append-only**. A record of what somebody agreed to at a moment
is worth nothing if a later run can quietly rewrite it, and the atlas digest is
what binds one to a specific set of pixels: change the art and the approval stops
matching, which is the behaviour the export gate is built on.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVED = "approved"
REJECTED = "rejected"
DECISIONS = (APPROVED, REJECTED)

HUMAN = "human"
AGENT = "agent"
DECIDERS = (HUMAN, AGENT)

# The gate that costs the most to get wrong, named once so a typo in a caller is
# a NameError here rather than a silently unopenable gate at export.
FINAL_AUDIT = "final-audit"
CONCEPT_SHEET = "concept-sheet"

# The two decisions a human must make whatever the decision mode. `final-audit`
# is enforced by export in code; `concept-sheet` fires only on the brainstorm
# route. A record claiming an agent made either is claiming a human approved
# pixels nobody looked at.
HUMAN_ONLY = (FINAL_AUDIT, CONCEPT_SHEET)

# The field names are `references/contract.md`'s, exactly. This module exists to
# collapse the number of shapes this file has, so it does not get to invent a
# new one: `approved_for` rather than `destination`, `approver_note` rather than
# `note`, `decided_at` rather than `timestamp`.
FIELDS = (
    "candidate_id",
    "approved_action",
    "approved_for",
    "source",
    "prompt_file",
    "atlas_digest",
    "decision",
    "decided_by",
    "approver_note",
    "decided_at",
)


def approvals_path(bundle: Path) -> Path:
    return bundle / "qa" / "approvals.json"


def read_approvals(bundle: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Every recorded decision, and why not when the file cannot be read.

    Returns `(entries, problem)`. `problem` is None when the file was read fine
    and simply holds nothing -- the ordinary case for a fresh bundle. It is a
    sentence when the file exists and cannot be trusted, because four different
    states used to collapse into one empty answer: file absent, file unparseable,
    file parseable but not a top-level list, and file correct but holding nothing
    that matches. A caller reporting the fourth for all four sends a reader
    hunting for a missing approval that is sitting right there in a file whose
    shape is wrong.
    """
    path = approvals_path(bundle)
    if not path.is_file():
        return [], f"{path} does not exist"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [], f"{path} is not valid JSON: {error}"
    if isinstance(loaded, dict) and isinstance(loaded.get("approvals"), list):
        return [], (
            f"{path} wraps its records in an `approvals` key. This schema is a top-level JSON "
            f"array, so nothing can find them in this shape. Re-record them with "
            f"`python geist_approvals.py {bundle} --action ...`, which writes the shape the "
            f"export gate reads."
        )
    if not isinstance(loaded, list):
        return [], (
            f"{path} holds a {type(loaded).__name__}, and this schema is a top-level JSON array "
            f"of decision records. The approval may well be in there; nothing can find it in "
            f"this shape."
        )
    return [entry for entry in loaded if isinstance(entry, dict)], None


def find_approval(
    bundle: Path, approved_action: str, atlas_digest: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """The approval for one action, optionally bound to one exact set of pixels."""
    entries, problem = read_approvals(bundle)
    if problem:
        return None, problem
    for entry in entries:
        if entry.get("approved_action") != approved_action:
            continue
        if entry.get("decision") != APPROVED:
            continue
        # `contract.md` says export enforces the human gate in code. It did not.
        # A record that explicitly claims an agent decided one of these is
        # rejected; one that omits the field is accepted, because bundles predate
        # it and silently invalidating their approvals would be a worse failure
        # than the one being fixed.
        if approved_action in HUMAN_ONLY and entry.get("decided_by") == AGENT:
            return None, (
                f"the only '{approved_action}' record is marked decided_by='agent'. This gate "
                f"is a human gate in both decision modes: it claims a human approved pixels "
                f"nobody looked at. Ask, then record the answer."
            )
        if atlas_digest is not None and entry.get("atlas_digest") != atlas_digest:
            continue
        return entry, None
    return None, None


def record_approval(
    bundle: Path,
    *,
    approved_action: str,
    decision: str = APPROVED,
    decided_by: str = HUMAN,
    candidate_id: str | None = None,
    approved_for: str | None = None,
    source: str | None = None,
    prompt_file: str | None = None,
    approver_note: str = "",
    atlas_digest: str | None = None,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Append one decision record in the shape `contract.md` documents.

    Every field SKILL.md's prose lists is here, and so are the three it did not:
    `approved_action` says which gate this opens, `decision` says which way the
    decision went, and `decided_by` says who made it. The first two are what the
    export gate matches on; none of the three was discoverable outside a reader.
    """
    if decision not in DECISIONS:
        raise SystemExit(f"decision must be one of {', '.join(DECISIONS)}; got '{decision}'")
    if decided_by not in DECIDERS:
        raise SystemExit(f"decided_by must be one of {', '.join(DECIDERS)}; got '{decided_by}'")
    if approved_action in HUMAN_ONLY and decided_by != HUMAN:
        raise SystemExit(
            f"'{approved_action}' is a human gate in both decision modes, so a record with "
            f"decided_by='{decided_by}' would claim a human approved pixels nobody looked at. "
            f"Ask, then record the answer."
        )

    entries, problem = read_approvals(bundle)
    if problem and approvals_path(bundle).is_file():
        # An unreadable file is not an empty one. Overwriting it would destroy a
        # record of a human decision to save a caller one manual step.
        raise SystemExit(
            f"refusing to append to an approvals file that cannot be read.\n  {problem}"
        )

    entry: dict[str, Any] = {
        "candidate_id": candidate_id,
        "approved_action": approved_action,
        "approved_for": approved_for,
        "source": source,
        "prompt_file": prompt_file,
        "atlas_digest": atlas_digest,
        "decision": decision,
        "decided_by": decided_by,
        "approver_note": approver_note,
        "decided_at": decided_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entry = {key: value for key, value in entry.items() if value is not None}

    entries.append(entry)
    path = approvals_path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--action", required=True, help="Gate this opens, e.g. final-audit or waiting")
    parser.add_argument("--decision", choices=DECISIONS, default=APPROVED)
    parser.add_argument(
        "--decided-by",
        choices=DECIDERS,
        default=HUMAN,
        help=f"Who decided. {' and '.join(HUMAN_ONLY)} must be human whatever the decision mode",
    )
    parser.add_argument("--candidate-id", help="Candidate id that was chosen")
    parser.add_argument("--approved-for", help="Where the approved art is promoted to")
    parser.add_argument("--source", help="What was looked at: a review page or a candidate image")
    parser.add_argument("--prompt-file", help="The prompt that drew it")
    parser.add_argument("--note", dest="approver_note", default="", help="The approver's own words")
    parser.add_argument("--atlas-digest", help="Binds a final-audit approval to exact pixels")
    parser.add_argument("--list", action="store_true", help="Print the recorded decisions and exit")
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    if args.list:
        entries, problem = read_approvals(bundle)
        print(json.dumps({"ok": problem is None, "problem": problem, "approvals": entries}, indent=2))
        raise SystemExit(0 if problem is None else 1)

    if args.action == FINAL_AUDIT and not args.atlas_digest:
        raise SystemExit(
            "a final-audit approval without --atlas-digest cannot open the export gate: the "
            "gate matches on the digest so that approving art and then changing it does not "
            "carry the approval across. Take the digest from qa/final-audit.json."
        )

    entry = record_approval(
        bundle,
        approved_action=args.action,
        decision=args.decision,
        decided_by=args.decided_by,
        candidate_id=args.candidate_id,
        approved_for=args.approved_for,
        source=args.source,
        prompt_file=args.prompt_file,
        approver_note=args.approver_note,
        atlas_digest=args.atlas_digest,
    )
    print(json.dumps({"ok": True, "recorded": entry, "file": str(approvals_path(bundle))}, indent=2))


if __name__ == "__main__":
    main()
