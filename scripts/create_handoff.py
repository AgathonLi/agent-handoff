#!/usr/bin/env python3
"""
Create a handoff document with auto-detected project metadata.

Pre-fills timestamp, project path, git branch, recent commits and modified
files, then leaves [TODO: ...] markers for the context only the outgoing agent
can supply.

Usage:
    python create_handoff.py [slug] [options]

    python create_handoff.py implementing-auth
    python create_handoff.py auth-part-2 --continues-from 2026-09-18-auth.md
    python create_handoff.py --handoff-dir docs/handoffs my-task
    python create_handoff.py                      # slug defaults to "handoff"

Options:
    --continues-from <file>   Link this handoff to a previous one
    --handoff-dir <path>      Override the handoff directory
    --project-root <path>     Override project root detection start point

The handoff directory is resolved by handoff_paths.resolve_handoff_dir; run
with any command to see which precedence level was used.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_paths import (  # noqa: E402
    ProjectRootNotFound,
    add_common_args,
    resolve_handoff_dir,
)


def run_cmd(cmd: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """Run a command and return (success, stdout)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        return result.returncode == 0, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, ""


def get_git_info(project_path: str) -> dict:
    """Gather git metadata. Returns empty defaults for non-git projects."""
    info = {
        "is_git_repo": False,
        "branch": None,
        "recent_commits": [],
        "modified_files": [],
        "staged_files": [],
    }

    success, _ = run_cmd(["git", "rev-parse", "--git-dir"], cwd=project_path)
    if not success:
        return info

    info["is_git_repo"] = True

    success, branch = run_cmd(["git", "branch", "--show-current"], cwd=project_path)
    if success and branch:
        info["branch"] = branch

    success, log = run_cmd(
        ["git", "log", "--oneline", "-5", "--no-decorate"], cwd=project_path
    )
    if success and log:
        info["recent_commits"] = log.split("\n")

    success, modified = run_cmd(["git", "diff", "--name-only"], cwd=project_path)
    if success and modified:
        info["modified_files"] = modified.split("\n")

    success, staged = run_cmd(
        ["git", "diff", "--name-only", "--cached"], cwd=project_path
    )
    if success and staged:
        info["staged_files"] = staged.split("\n")

    return info


def find_previous_handoffs(handoff_dir: Path) -> list[dict]:
    """List existing handoffs in the resolved directory, newest first."""
    if not handoff_dir.is_dir():
        return []

    handoffs = []
    for filepath in handoff_dir.glob("*.md"):
        try:
            content = filepath.read_text(encoding="utf-8")
            match = re.search(r"^#\s+(?:Handoff:\s*)?(.+)$", content, re.MULTILINE)
            title = match.group(1).strip() if match else filepath.stem
        except (OSError, UnicodeDecodeError):
            title = filepath.stem

        date_match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d{6})", filepath.name)
        date = None
        if date_match:
            try:
                date = datetime.strptime(
                    f"{date_match.group(1)} {date_match.group(2)}",
                    "%Y-%m-%d %H%M%S",
                )
            except ValueError:
                date = None

        handoffs.append(
            {
                "filename": filepath.name,
                "path": str(filepath),
                "title": title,
                "date": date,
            }
        )

    handoffs.sort(key=lambda x: x["date"] or datetime.min, reverse=True)
    return handoffs


def get_previous_handoff_info(
    handoff_dir: Path, continues_from: str | None = None
) -> dict:
    """Resolve chain linkage information for the new handoff."""
    handoffs = find_previous_handoffs(handoff_dir)

    if continues_from:
        for h in handoffs:
            if continues_from in h["filename"]:
                return {
                    "exists": True,
                    "filename": h["filename"],
                    "title": h["title"],
                }
        return {"exists": False, "filename": continues_from, "title": "Not found"}

    if handoffs:
        most_recent = handoffs[0]
        return {
            "exists": True,
            "filename": most_recent["filename"],
            "title": most_recent["title"],
            "suggested": True,
        }

    return {"exists": False}


def sanitize_slug(slug: str | None) -> str:
    """Normalize a slug to lowercase alphanumerics and hyphens."""
    if not slug:
        return "handoff"
    slug = slug.lower().replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "handoff"


def build_content(
    project_root: Path,
    git_info: dict,
    prev_handoff: dict,
    timestamp: str,
) -> str:
    """Assemble the handoff document body.

    All required and recommended section headers are level 2 ("## "). The
    validator treats levels 1 through 3 as section headers, so level 4 ("#### ")
    is the safe choice for any sub-heading you add by hand inside a section.
    """
    branch_line = git_info["branch"] or "[not a git repo or detached HEAD]"

    if git_info["recent_commits"]:
        commits_section = "\n".join(f"  - {c}" for c in git_info["recent_commits"])
    else:
        commits_section = "  - [no recent commits or not a git repo]"

    all_modified = sorted(set(git_info["modified_files"] + git_info["staged_files"]))
    if all_modified:
        modified_section = "\n".join(
            f"| {f} | [describe changes] | [why changed] |" for f in all_modified[:10]
        )
        if len(all_modified) > 10:
            modified_section += (
                f"\n| ... and {len(all_modified) - 10} more files | | |"
            )
    else:
        modified_section = "| [no modified files detected] | | |"

    if prev_handoff.get("exists"):
        chain_body = (
            f"- **Continues from**: "
            f"[{prev_handoff['filename']}](./{prev_handoff['filename']})\n"
            f"  - Previous title: {prev_handoff.get('title', 'Unknown')}\n"
            f'- **Supersedes**: [list any older handoffs this replaces, or "None"]\n\n'
            f"> Review the previous handoff for full context before filling this one."
        )
    else:
        chain_body = (
            "- **Continues from**: None (fresh start)\n"
            "- **Supersedes**: None\n\n"
            "> This is the first handoff for this task."
        )

    return f"""# Handoff: [TASK_TITLE - replace this]

## Session Metadata

- Created: {timestamp}
- Project: {project_root}
- Branch: {branch_line}
- Session duration: [estimate how long you worked]

Recent commits for context:

{commits_section}

## Handoff Chain

{chain_body}

## Current State Summary

[TODO: One paragraph describing what was being worked on, current status, and where things left off. Needs at least 50 characters of real content to pass validation.]

## Architecture Overview

[TODO: Key architectural insights discovered during this session - structure, main components, data flow]

## Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| [TODO: Add critical files] | | |

## Key Patterns Discovered

[TODO: Patterns, conventions or idioms in this codebase the next agent should follow]

## Tasks Finished

- [ ] [TODO: List completed tasks]

## Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
{modified_section}

## Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| [TODO: Document key decisions] | | |

## Immediate Next Steps

1. [TODO: Most critical next action]
2. [TODO: Second priority]
3. [TODO: Third priority]

## Blockers and Open Questions

- [ ] [TODO: List any blockers or open questions]

## Deferred Items

- [TODO: Items deferred and why]

## Important Context

[TODO: The most important section. Write the critical information the next agent MUST know. Needs at least 50 characters of real content to pass validation.]

## Assumptions Made

- [TODO: List assumptions made during this session]

## Potential Gotchas

- [TODO: Things that might trip up a new agent - edge cases, quirks, non-obvious behaviour]

## Environment State

[TODO: Tools and services used, active processes, and relevant environment variable NAMES only - never actual values or secrets]

## Related Resources

- [TODO: Links to relevant docs and files]

---

**Security reminder**: run `validate_handoff.py` before finalizing to check for
accidental secret exposure and incomplete sections.
"""


def generate_handoff(
    handoff_dir: Path,
    project_root: Path,
    slug: str | None = None,
    continues_from: str | None = None,
) -> str:
    """Write a new handoff document and return its path."""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y-%m-%d-%H%M%S")

    filename = f"{file_timestamp}-{sanitize_slug(slug)}.md"
    filepath = handoff_dir / filename

    git_info = get_git_info(str(project_root))
    prev_handoff = get_previous_handoff_info(handoff_dir, continues_from)
    content = build_content(project_root, git_info, prev_handoff, timestamp)

    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a handoff document with auto-detected project metadata."
    )
    parser.add_argument(
        "slug",
        nargs="?",
        default=None,
        help="Short identifier for the handoff (e.g. 'implementing-auth')",
    )
    parser.add_argument(
        "--continues-from",
        dest="continues_from",
        metavar="FILE",
        help="Filename of the previous handoff this continues from",
    )
    add_common_args(parser)
    args = parser.parse_args()

    try:
        handoff_dir, project_root, source = resolve_handoff_dir(
            explicit=args.handoff_dir,
            start=args.project_root,
            create=True,
        )
    except ProjectRootNotFound as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Project root:  {project_root}")
    print(f"Handoff dir:   {handoff_dir}")
    print(f"Resolved via:  {source}\n")

    if not args.continues_from:
        previous = find_previous_handoffs(handoff_dir)
        if previous:
            print(f"Found {len(previous)} existing handoff(s).")
            print(f"Most recent: {previous[0]['filename']}")
            print("Use --continues-from <filename> to link them.\n")

    filepath = generate_handoff(
        handoff_dir, project_root, args.slug, args.continues_from
    )

    print(f"Created handoff document: {filepath}\n")
    print("Next steps:")
    print(f"  1. Open {filepath}")
    print("  2. Replace every [TODO: ...] placeholder with real content")
    print("  3. Prioritize 'Important Context' and 'Immediate Next Steps'")
    print(f"  4. Run: python validate_handoff.py \"{filepath}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
