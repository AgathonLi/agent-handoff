#!/usr/bin/env python3
"""
List handoff documents available in a project.

Displays date, title, completion status and size for each handoff, newest
first, and reports which precedence level resolved the handoff directory.

Usage:
    python list_handoffs.py [options]

    python list_handoffs.py
    python list_handoffs.py --project-root /path/to/project
    python list_handoffs.py --handoff-dir docs/handoffs
    python list_handoffs.py --json

Options:
    --handoff-dir <path>    Override the handoff directory
    --project-root <path>   Override project root detection start point
    --json                  Emit machine-readable JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_paths import (  # noqa: E402
    ProjectRootNotFound,
    add_common_args,
    resolve_handoff_dir,
)


def extract_title(filepath: Path) -> str:
    """Read the H1 title from a handoff document."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "[unable to read title]"

    match = re.search(r"^#\s+(?:Handoff:\s*)?(.+)$", content, re.MULTILINE)
    if not match:
        return "[no title found]"

    title = match.group(1).strip()
    if title.startswith("[") and title.endswith("]"):
        return "[untitled - needs completion]"
    return title[:60] + "..." if len(title) > 60 else title


def check_completion_status(filepath: Path) -> str:
    """Summarize completion based on remaining TODO markers."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "Unknown"

    todo_count = content.count("[TODO:")
    if todo_count == 0:
        return "Complete"
    if todo_count <= 3:
        return f"In progress ({todo_count} TODOs)"
    return f"Needs work ({todo_count} TODOs)"


def parse_date_from_filename(filename: str) -> datetime | None:
    """Parse the timestamp prefix from a handoff filename."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d{6})", filename)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H%M%S"
        )
    except ValueError:
        return None


def collect_handoffs(handoff_dir: Path) -> list[dict]:
    """Gather handoff metadata from the directory, newest first."""
    if not handoff_dir.is_dir():
        return []

    handoffs = []
    for filepath in handoff_dir.glob("*.md"):
        handoffs.append(
            {
                "path": str(filepath),
                "filename": filepath.name,
                "title": extract_title(filepath),
                "status": check_completion_status(filepath),
                "date": parse_date_from_filename(filepath.name),
                "size": filepath.stat().st_size,
            }
        )

    handoffs.sort(key=lambda x: x["date"] or datetime.min, reverse=True)
    return handoffs


def format_date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "unknown date"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List handoff documents available in a project."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON instead of a formatted list",
    )
    add_common_args(parser)
    args = parser.parse_args()

    try:
        handoff_dir, project_root, source = resolve_handoff_dir(
            explicit=args.handoff_dir,
            start=args.project_root,
            create=False,
        )
    except ProjectRootNotFound as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    handoffs = collect_handoffs(handoff_dir)

    if args.as_json:
        print(
            json.dumps(
                {
                    "project_root": str(project_root),
                    "handoff_dir": str(handoff_dir),
                    "resolved_via": source,
                    "count": len(handoffs),
                    "handoffs": handoffs,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    print(f"Project root:  {project_root}")
    print(f"Handoff dir:   {handoff_dir}")
    print(f"Resolved via:  {source}\n")

    if not handoffs:
        print("No handoffs found.")
        print("\nCreate one with: python create_handoff.py [slug]")
        return 0

    print(f"Found {len(handoffs)} handoff(s)\n")
    print("-" * 78)
    for h in handoffs:
        print(f"  Date:   {format_date(h['date'])}")
        print(f"  Title:  {h['title']}")
        print(f"  Status: {h['status']}")
        print(f"  File:   {h['filename']}")
        print("-" * 78)

    print(f"\nMost recent: {handoffs[0]['path']}")
    print("Check freshness with: python check_staleness.py <file>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
