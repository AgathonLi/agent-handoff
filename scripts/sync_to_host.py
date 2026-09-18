#!/usr/bin/env python3
"""
Sync this development repository to the installed skill locations.

Direction is one-way: repository -> host skill directory. The repository is the
source of truth; an installed copy is a build artifact.

Why not a symlink
-----------------
A symlink or junction would keep the two in lockstep with no command to run, but
it also exposes the repository's own development files to the host: .git/,
tests/, and most importantly AGENTS.md. That last one is a correctness problem,
not a tidiness problem -- see below.

Why AGENTS.md must not be copied
--------------------------------
AGENTS.md is one of the project-root markers that handoff_paths.py looks for.
Placing it inside the installed skill directory would make that directory look
like a legitimate project root, so running a script from there would write
handoff documents into the skill's own directory instead of failing loudly.
That is the exact defect this skill was built to avoid. EXCLUDED_NAMES enforces
the exclusion; test_sync_excludes_root_markers locks the behaviour.

Usage
-----
    python scripts/sync_to_host.py            # dry run, prints planned changes
    python scripts/sync_to_host.py --apply    # perform the sync
    python scripts/sync_to_host.py --target <path> --apply
    python scripts/sync_to_host.py --apply --prune   # also delete stale files
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import os
import shutil
import sys
from pathlib import Path

# Candidate install locations, probed in order. Every existing one is synced.
DEFAULT_TARGETS = [
    Path.home() / ".workbuddy" / "skills" / "agent-handoff",
    Path.home() / ".claude" / "skills" / "agent-handoff",
    Path.home() / ".agents" / "skills" / "agent-handoff",
]

# Files and directories that belong to development only and must never reach an
# installed copy. AGENTS.md is excluded for correctness, not neatness.
EXCLUDED_NAMES = {
    ".git",
    ".github",
    ".gitattributes",
    ".handoff",
    "__pycache__",
    "AGENTS.md",
    "tests",
    "sync_to_host.py",
}

# Files the host writes at install time. Present in the target, absent from the
# repository; --prune must not treat them as stale.
HOST_OWNED_NAMES = {
    "_meta.json",
    "_skillhub_meta.json",
}


def repo_root() -> Path:
    """The repository root, derived from this file's location."""
    return Path(__file__).resolve().parent.parent


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_payload(root: Path) -> dict[str, Path]:
    """Map relative POSIX path -> absolute source path for everything to sync."""
    payload: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_NAMES]
        for name in filenames:
            if name in EXCLUDED_NAMES:
                continue
            absolute = Path(dirpath) / name
            relative = absolute.relative_to(root).as_posix()
            payload[relative] = absolute
    return payload


def collect_existing(target: Path) -> set[str]:
    """Relative paths already present in the target, excluding host-owned files."""
    existing: set[str] = set()
    if not target.exists():
        return existing
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for name in filenames:
            if name in HOST_OWNED_NAMES:
                continue
            absolute = Path(dirpath) / name
            existing.add(absolute.relative_to(target).as_posix())
    return existing


def plan(payload: dict[str, Path], target: Path, prune: bool) -> dict[str, list[str]]:
    """Classify each path as new, changed, unchanged or stale."""
    existing = collect_existing(target)
    actions: dict[str, list[str]] = {
        "new": [],
        "changed": [],
        "unchanged": [],
        "stale": [],
    }

    for relative, source in sorted(payload.items()):
        destination = target / relative
        if not destination.exists():
            actions["new"].append(relative)
        elif filecmp.cmp(source, destination, shallow=False):
            actions["unchanged"].append(relative)
        else:
            actions["changed"].append(relative)

    if prune:
        actions["stale"] = sorted(existing - set(payload))

    return actions


def apply_plan(
    payload: dict[str, Path],
    target: Path,
    actions: dict[str, list[str]],
) -> None:
    for relative in actions["new"] + actions["changed"]:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload[relative], destination)

    for relative in actions["stale"]:
        (target / relative).unlink(missing_ok=True)


def verify(payload: dict[str, Path], target: Path) -> list[str]:
    """Re-read both sides and report any path that does not match."""
    mismatched = []
    for relative, source in payload.items():
        destination = target / relative
        if not destination.exists() or _digest(source) != _digest(destination):
            mismatched.append(relative)
    return sorted(mismatched)


def resolve_targets(explicit: str | None) -> list[Path]:
    if explicit:
        return [Path(explicit).expanduser().resolve()]
    return [t for t in DEFAULT_TARGETS if t.exists()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync this repository to the installed skill directories."
    )
    parser.add_argument(
        "--target",
        help="Sync to this path only, instead of probing the known locations.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes. Without this flag the run is a dry run.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Also delete target files that no longer exist in the repository.",
    )
    args = parser.parse_args()

    root = repo_root()
    payload = collect_payload(root)
    targets = resolve_targets(args.target)

    print(f"Source:  {root}")
    print(f"Files:   {len(payload)}")
    print(f"Mode:    {'APPLY' if args.apply else 'DRY RUN'}")
    excluded = ", ".join(sorted(EXCLUDED_NAMES))
    print(f"Skipped: {excluded}")

    if not targets:
        print("\nNo installed skill directory found. Nothing to do.")
        print("Candidates probed:")
        for candidate in DEFAULT_TARGETS:
            print(f"  {candidate}")
        return 0

    failures = 0

    for target in targets:
        print(f"\n--- {target} ---")
        actions = plan(payload, target, args.prune)

        for label in ("new", "changed", "stale"):
            for relative in actions[label]:
                print(f"  {label:9} {relative}")
        print(f"  unchanged {len(actions['unchanged'])} file(s)")

        pending = actions["new"] + actions["changed"] + actions["stale"]
        if not pending:
            print("  already in sync")
            continue

        if not args.apply:
            print(f"  {len(pending)} change(s) pending; re-run with --apply")
            continue

        target.mkdir(parents=True, exist_ok=True)
        apply_plan(payload, target, actions)

        mismatched = verify(payload, target)
        if mismatched:
            failures += 1
            print(f"  [FAIL] {len(mismatched)} file(s) did not match after copy:")
            for relative in mismatched:
                print(f"           {relative}")
        else:
            print(f"  [OK] {len(pending)} change(s) applied and verified")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
