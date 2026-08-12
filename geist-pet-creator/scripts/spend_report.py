#!/usr/bin/env python3
"""Read the spend ledgers, and record a line for a draw this script did not make.

Reporting is the main job:

    spend_report.py /abs/path/PetName.pet          one Pet, from its own ledger
    spend_report.py /abs/path/work                 every *.pet under a directory
    spend_report.py --home                         every Pet this machine has built

It needs no credential, which is why it is not a flag on generate_candidates.py:
that script resolves an API key before it does any work, and reading a receipt
should not require one.

`--record` exists for Built-in Image Generation, where the agent draws with its
own capability and no provider response reports a price. Those lines carry
`cost_usd: null`, so the image count stays visible and the two image-generation
modes stay comparable:

    spend_report.py --record --pet /abs/path/PetName.pet \\
        --action waiting --images 6 --unpriced --mode auto --model builtin-imagegen
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from geist_spend import (
    KIND_DRAW,
    KIND_VERIFY,
    MODES,
    SpendLedger,
    bundle_ledger,
    home_ledger,
    pet_id_for,
    read_ledger,
    resolve_targets,
    rollup,
)


def print_table(pets: dict[str, dict], malformed: int, by_action: bool) -> None:
    if not pets:
        print("no ledger lines found")
        return

    width = max(len("PET"), max(len(key) for key in pets))
    print(f"{'PET'.ljust(width)}  {'CALLS':>6}  {'IMAGES':>6}  {'COST USD':>10}  {'UNPRICED':>8}  FIRST                 LAST")
    total_calls = total_images = total_unpriced = 0
    total_cost = 0.0
    for key in sorted(pets):
        entry = pets[key]
        print(
            f"{key.ljust(width)}  {entry['calls']:>6}  {entry['images']:>6}  "
            f"{entry['cost_usd']:>10.4f}  {entry['unpriced_images']:>8}  "
            f"{entry['first'] or '-':<20}  {entry['last'] or '-'}"
        )
        total_calls += entry["calls"]
        total_images += entry["images"]
        total_cost += entry["cost_usd"]
        total_unpriced += entry["unpriced_images"]
        if by_action:
            for action in sorted(entry["actions"]):
                stats = entry["actions"][action]
                print(
                    f"{'  ' + action:<{width}}  {stats['calls']:>6}  {stats['images']:>6}  "
                    f"{stats['cost_usd']:>10.4f}"
                )
    if len(pets) > 1:
        print(
            f"{'TOTAL'.ljust(width)}  {total_calls:>6}  {total_images:>6}  "
            f"{total_cost:>10.4f}  {total_unpriced:>8}"
        )
    if total_unpriced:
        print(
            f"\n{total_unpriced} image(s) are unpriced: drawn by a built-in capability that "
            "reports no cost. They are counted, never estimated."
        )
    if malformed:
        print(f"\n{malformed} malformed line(s) skipped.")


def do_record(args: argparse.Namespace) -> None:
    if args.cost_usd is None and not args.unpriced:
        raise SystemExit(
            "--record needs either --cost-usd or --unpriced. A missing price is not zero, "
            "and a zero in a file that reads like a receipt is a lie."
        )
    if args.cost_usd is not None and args.unpriced:
        raise SystemExit("--cost-usd and --unpriced contradict each other; pass one")
    if args.pet is None and args.kind == KIND_DRAW:
        raise SystemExit("--record --kind draw needs --pet: a drawn frame belongs to a Pet")

    bundle = Path(args.pet).expanduser().resolve() if args.pet else None
    if bundle is not None and not bundle.is_dir():
        raise SystemExit(f"{bundle} is not a bundle directory")

    ledger = SpendLedger(
        model=args.model,
        mode=args.mode,
        action=args.action,
        bundle=bundle,
        kind=args.kind,
        provider=args.provider,
        candidate_id=args.candidate_id,
    )
    ledger.record(None if args.unpriced else args.cost_usd, images=args.images, note=args.note)
    print(json.dumps({"ok": True, "recorded": args.images, **ledger.as_dict()}, indent=2))
    for warning in ledger.warnings:
        print(f"warning: {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="Pet bundles, ledger files, or a directory holding bundles")
    parser.add_argument("--home", action="store_true", help=f"Read the machine-wide ledger at {home_ledger()}")
    parser.add_argument("--by-action", action="store_true", help="Break each Pet down by action")
    parser.add_argument("--json", action="store_true", help="Emit the rollup as JSON")

    record = parser.add_argument_group("--record (Built-in Image Generation)")
    record.add_argument("--record", action="store_true", help="Append a line instead of reading")
    record.add_argument("--pet", help="Bundle the draw belongs to")
    record.add_argument("--action", help="Phase drawn: concept-sheet, canonical-base, or a sprite action")
    record.add_argument("--images", type=int, default=1, help="How many images this line accounts for")
    record.add_argument("--cost-usd", type=float, help="Measured cost, when one is known")
    record.add_argument("--unpriced", action="store_true", help="No price is reported for these images")
    record.add_argument("--mode", choices=MODES, help="Decision mode this draw ran under")
    record.add_argument("--model", default="builtin-imagegen", help="What drew it")
    record.add_argument("--provider", default="builtin", help="Provider name for the line")
    record.add_argument("--kind", choices=(KIND_DRAW, KIND_VERIFY), default=KIND_DRAW)
    record.add_argument("--candidate-id", help="Candidate packet this draw belongs to")
    record.add_argument("--note", help="Short free-text note")

    args = parser.parse_args()

    if args.record:
        do_record(args)
        return

    if args.home and args.paths:
        # Both files hold the same lines, so summing them would double every
        # number in the report.
        raise SystemExit(
            "--home already contains the lines a bundle ledger holds; ask for one or the other "
            "so the totals stay arithmetic"
        )

    targets = [home_ledger()] if args.home else resolve_targets(args.paths)
    if not targets:
        raise SystemExit("nothing to read: pass a bundle, a ledger file, a directory of bundles, or --home")

    records: list[dict] = []
    malformed = 0
    missing: list[Path] = []
    for target in targets:
        found, bad = read_ledger(target)
        if not found and not bad and not target.is_file():
            missing.append(target)
        records.extend(found)
        malformed += bad

    pets = rollup(records)
    if args.json:
        printable = {
            key: {
                **entry,
                "cost_usd": round(entry["cost_usd"], 6),
                "models": sorted(entry["models"]),
                "bundles": sorted(entry["bundles"]),
            }
            for key, entry in pets.items()
        }
        print(json.dumps({"pets": printable, "malformed_lines": malformed,
                          "ledgers_read": [str(path) for path in targets]}, indent=2))
        return

    print_table(pets, malformed, args.by_action)
    for path in missing:
        print(f"note: no ledger at {path}")


if __name__ == "__main__":
    main()
