#!/usr/bin/env python3
"""Manage Geist Pet Creator's isolated Python runtime.

The runtime lives in the user's cache. It never modifies system Python and it
never uses sudo. Run `install` only after the user has approved the dependency
download described by the skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SKILL_ID = "geist-pet-creator"
RUNTIME_VERSION = 1
SUPPORTED_PYTHON = {(3, 11), (3, 12), (3, 13), (3, 14)}
MARKER_NAME = ".geist-pet-creator-runtime.json"


def requirements_path() -> Path:
    return Path(__file__).resolve().parent.parent / "requirements.txt"


def requirements_digest() -> str:
    return hashlib.sha256(requirements_path().read_bytes()).hexdigest()


def cache_root() -> Path:
    override = os.environ.get("GEIST_PET_CREATOR_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser().resolve() / SKILL_ID
    return Path.home() / ".cache" / SKILL_ID


def runtime_dir() -> Path:
    version = f"py{sys.version_info.major}{sys.version_info.minor}"
    return cache_root() / f"runtime-{version}"


def runtime_python(directory: Path | None = None) -> Path:
    directory = directory or runtime_dir()
    if os.name == "nt":
        return directory / "Scripts" / "python.exe"
    return directory / "bin" / "python"


def marker_path(directory: Path | None = None) -> Path:
    return (directory or runtime_dir()) / MARKER_NAME


def expected_marker() -> dict[str, object]:
    return {
        "skill": SKILL_ID,
        "runtime_version": RUNTIME_VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "requirements_sha256": requirements_digest(),
    }


def read_marker(directory: Path | None = None) -> dict[str, object] | None:
    path = marker_path(directory)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def supported_python() -> bool:
    return (sys.version_info.major, sys.version_info.minor) in SUPPORTED_PYTHON


def inspect_runtime() -> tuple[bool, str]:
    if not supported_python():
        return False, "Python 3.11, 3.12, 3.13, or 3.14 is required"
    directory = runtime_dir()
    python = runtime_python(directory)
    marker = read_marker(directory)
    if not directory.exists():
        return False, "isolated runtime is not installed"
    if marker != expected_marker():
        return False, "isolated runtime is stale or has no valid ownership marker; run repair"
    if not python.is_file():
        return False, "isolated runtime has no Python executable; run repair"
    result = subprocess.run(
        [str(python), "-c", "from PIL import Image; print(Image.__version__)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return False, "Pillow import failed; run repair"
    return True, f"ready (Pillow {result.stdout.strip()})"


def safe_to_remove(directory: Path) -> bool:
    marker = read_marker(directory)
    return bool(marker and marker.get("skill") == SKILL_ID)


def build_runtime(destination: Path) -> None:
    if not supported_python():
        raise SystemExit("Python 3.11, 3.12, 3.13, or 3.14 is required")
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{destination.name}.install-{os.getpid()}"
    if temporary.exists():
        if not safe_to_remove(temporary):
            raise SystemExit(f"refusing to replace unowned temporary directory: {temporary}")
        shutil.rmtree(temporary)
    try:
        temporary.mkdir()
        marker_path(temporary).write_text(
            json.dumps(expected_marker(), indent=2) + "\n", encoding="utf-8"
        )
        venv.EnvBuilder(with_pip=True, clear=False).create(temporary)
        python = runtime_python(temporary)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                str(requirements_path()),
            ],
            check=True,
        )
        temporary.rename(destination)
    except BaseException:
        if temporary.exists() and safe_to_remove(temporary):
            shutil.rmtree(temporary)
        raise


def install() -> None:
    ready, detail = inspect_runtime()
    if ready:
        print(f"Geist Pet Creator runtime {detail}: {runtime_python()}")
        return
    destination = runtime_dir()
    if destination.exists():
        raise SystemExit(f"{detail}. Run `bootstrap_runtime.py repair`.")
    print(f"Installing pinned dependencies into isolated runtime: {destination}")
    build_runtime(destination)
    print(f"Installed: {runtime_python(destination)}")


def repair() -> None:
    destination = runtime_dir()
    if destination.exists():
        if not safe_to_remove(destination):
            raise SystemExit(f"refusing to remove unowned directory: {destination}")
        shutil.rmtree(destination)
    print(f"Rebuilding isolated runtime: {destination}")
    build_runtime(destination)
    print(f"Repaired: {runtime_python(destination)}")


def remove(confirmed: bool) -> None:
    if not confirmed:
        raise SystemExit("remove requires --yes; Pet bundles and exported Pets are never removed")
    destination = runtime_dir()
    if not destination.exists():
        print("Runtime is already absent. Pet bundles were not touched.")
        return
    if not safe_to_remove(destination):
        raise SystemExit(f"refusing to remove unowned directory: {destination}")
    shutil.rmtree(destination)
    print(f"Removed runtime: {destination}. Pet bundles were not touched.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Check whether the isolated runtime is ready")
    subparsers.add_parser("install", help="Create the isolated runtime and install pinned dependencies")
    subparsers.add_parser("repair", help="Rebuild a runtime owned by this skill")
    subparsers.add_parser("python", help="Print the isolated Python executable")
    remove_parser = subparsers.add_parser("remove", help="Remove only the isolated runtime")
    remove_parser.add_argument("--yes", action="store_true", help="Confirm runtime removal")
    args = parser.parse_args()

    if args.command == "check":
        ready, detail = inspect_runtime()
        print(f"{SKILL_ID}: {detail}")
        raise SystemExit(0 if ready else 1)
    if args.command == "install":
        install()
        return
    if args.command == "repair":
        repair()
        return
    if args.command == "python":
        ready, detail = inspect_runtime()
        if not ready:
            raise SystemExit(f"{detail}; run install first")
        print(runtime_python())
        return
    if args.command == "remove":
        remove(args.yes)


if __name__ == "__main__":
    main()
