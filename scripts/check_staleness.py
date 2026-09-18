#!/usr/bin/env python3
"""
Assess whether a handoff document still reflects the current project state.

Signals used:
    - Age of the handoff
    - Commits since the handoff (git projects)
    - Files changed since the handoff (git projects)
    - Branch divergence (git projects)
    - Referenced files that no longer exist (all projects)
    - Files modified after the handoff timestamp (non-git fallback)

Usage:
    python check_staleness.py <handoff-file> [options]

    python check_staleness.py .handoff/2026-09-18-120000-auth.md
    python check_staleness.py my-handoff.md --project-root /path/to/project

Options:
    --handoff-dir <path>    Override the handoff directory
    --project-root <path>   Override project root detection start point
    --json                  Emit machine-readable JSON

Exit codes:
    0  FRESH or SLIGHTLY_STALE
    1  STALE
    2  VERY_STALE or resolution failure

Non-git projects
----------------
Git history is the strongest staleness signal, but its absence is a property of
the project, not a failure of this check. When no git repository is present the
check falls back to filesystem modification times so a useful verdict is still
produced. The verdict names which signal was used.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_paths import (  # noqa: E402
    ProjectRootNotFound,
    add_common_args,
    find_project_root,
)

# Directories never worth scanning in the non-git fallback.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".cache",
    "target",
    ".handoff",
    ".claude",
    ".workbuddy",
}

MAX_SCAN_FILES = 5000


def run_cmd(cmd: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """Run a command and return (success, stdout)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=10
        )
        return result.returncode == 0, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, ""


def parse_handoff_metadata(filepath: Path) -> dict:
    """Extract metadata recorded in the handoff's Session Metadata section."""
    metadata: dict = {
        "created": None,
        "branch": None,
        "project_path": None,
        "modified_files": [],
    }

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return metadata

    match = re.search(r"Created:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", content)
    if match:
        try:
            metadata["created"] = datetime.strptime(
                match.group(1), "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            pass

    match = re.search(r"Branch:\s*(\S+)", content)
    if match and not match.group(1).startswith("["):
        metadata["branch"] = match.group(1)

    match = re.search(r"Project:\s*(.+?)(?:\n|$)", content)
    if match:
        metadata["project_path"] = match.group(1).strip()

    for f in re.findall(r"\|\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)\s*\|", content):
        if "/" in f and not f.startswith("["):
            metadata["modified_files"].append(f)

    return metadata


def resolve_project_path(
    handoff_file: Path, metadata: dict, override: str | None
) -> tuple[Path, str]:
    """Determine the project root to compare the handoff against.

    Precedence: explicit override, then the path recorded inside the handoff,
    then marker-based detection from the handoff's location. Parent-directory
    counting is deliberately not used; it silently breaks whenever the handoff
    directory depth differs from the layout the counting assumed.
    """
    if override:
        return Path(override).expanduser().resolve(), "explicit --project-root"

    recorded = metadata.get("project_path")
    if recorded:
        candidate = Path(recorded)
        if candidate.is_dir():
            return candidate.resolve(), "recorded in handoff metadata"

    try:
        root = find_project_root(handoff_file.parent)
        return root, "detected from handoff file location"
    except ProjectRootNotFound:
        return handoff_file.parent.resolve(), "fallback: handoff file directory"


def get_commits_since(timestamp: datetime | None, project_path: Path) -> list[str]:
    """List commits authored after the handoff timestamp."""
    if not timestamp:
        return []
    iso_time = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    success, output = run_cmd(
        ["git", "log", f"--since={iso_time}", "--oneline", "--no-decorate"],
        cwd=str(project_path),
    )
    return output.split("\n") if success and output else []


def get_changed_files_since(
    timestamp: datetime | None, project_path: Path
) -> list[str]:
    """List files touched by commits after the handoff timestamp."""
    if not timestamp:
        return []
    iso_time = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    success, output = run_cmd(
        ["git", "log", f"--since={iso_time}", "--name-only", "--pretty=format:"],
        cwd=str(project_path),
    )
    if not (success and output):
        return []
    return sorted({f.strip() for f in output.split("\n") if f.strip()})


def get_mtime_changed_files(
    timestamp: datetime | None, project_path: Path
) -> tuple[list[str], bool]:
    """Non-git fallback: find files modified after the handoff timestamp.

    Returns (files, truncated) where `truncated` indicates the scan hit
    MAX_SCAN_FILES and the result is a lower bound.
    """
    if not timestamp:
        return [], False

    cutoff = timestamp.timestamp()
    changed: list[str] = []
    scanned = 0

    for path in project_path.rglob("*"):
        if scanned >= MAX_SCAN_FILES:
            return changed, True
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        scanned += 1
        try:
            if path.stat().st_mtime > cutoff:
                changed.append(str(path.relative_to(project_path)))
        except OSError:
            continue

    return changed, False


def check_files_exist(files: list[str], project_path: Path) -> tuple[list[str], list[str]]:
    """Split referenced files into existing and missing."""
    existing, missing = [], []
    for f in files:
        if (project_path / f).exists():
            existing.append(f)
        else:
            missing.append(f)
    return existing, missing


def calculate_staleness_level(
    days_old: float,
    commits_since: int,
    files_changed: int,
    branch_matches: bool,
    files_missing: int,
) -> tuple[str, str, list[str]]:
    """Score staleness and produce a recommendation.

    Thresholds reflect typical development rhythms: 1 day of active work,
    7 days as a sprint boundary, 30 days as likely stale. Each signal
    contributes 1-3 points; the total maps to four levels.
    """
    issues: list[str] = []
    score = 0

    if days_old > 30:
        score += 3
        issues.append(f"Handoff is {int(days_old)} days old")
    elif days_old > 7:
        score += 2
        issues.append(f"Handoff is {int(days_old)} days old")
    elif days_old > 1:
        score += 1

    if commits_since > 50:
        score += 3
        issues.append(f"{commits_since} commits since handoff - significant changes")
    elif commits_since > 20:
        score += 2
        issues.append(f"{commits_since} commits since handoff")
    elif commits_since > 5:
        score += 1

    if not branch_matches:
        score += 2
        issues.append("Current branch differs from the handoff branch")

    if files_missing > 5:
        score += 2
        issues.append(f"{files_missing} referenced files no longer exist")
    elif files_missing > 0:
        score += 1
        issues.append(f"{files_missing} referenced file(s) missing")

    if files_changed > 20:
        score += 2
        issues.append(f"{files_changed} files changed since handoff")
    elif files_changed > 5:
        score += 1

    if score == 0:
        return "FRESH", "Safe to resume - minimal changes since handoff", issues
    if score <= 2:
        return (
            "SLIGHTLY_STALE",
            "Generally safe to resume - review changes before continuing",
            issues,
        )
    if score <= 4:
        return (
            "STALE",
            "Proceed with caution - significant changes may affect context",
            issues,
        )
    return (
        "VERY_STALE",
        "Consider creating a fresh handoff - too many changes since the original",
        issues,
    )


def check_staleness(handoff_path: str, project_root: str | None = None) -> dict:
    """Run the staleness assessment."""
    path = Path(handoff_path).expanduser()
    if not path.exists():
        return {"error": f"Handoff file not found: {handoff_path}"}

    metadata = parse_handoff_metadata(path)
    project_path, path_source = resolve_project_path(path, metadata, project_root)

    is_git_repo, _ = run_cmd(["git", "rev-parse", "--git-dir"], cwd=str(project_path))

    result: dict = {
        "handoff_file": str(path.resolve()),
        "project_path": str(project_path),
        "project_path_source": path_source,
        "is_git_repo": is_git_repo,
        "created": metadata["created"],
        "handoff_branch": metadata["branch"],
        "signal": "git history" if is_git_repo else "file modification times",
    }

    if metadata["created"]:
        age = datetime.now() - metadata["created"]
        result["days_old"] = age.total_seconds() / 86400
        result["hours_old"] = age.total_seconds() / 3600
    else:
        result["days_old"] = None
        result["hours_old"] = None

    existing, missing = check_files_exist(metadata["modified_files"], project_path)
    result["referenced_files_exist"] = len(existing)
    result["referenced_files_missing"] = missing

    if is_git_repo:
        success, branch = run_cmd(
            ["git", "branch", "--show-current"], cwd=str(project_path)
        )
        result["current_branch"] = branch if success else None
        result["branch_matches"] = (
            result["current_branch"] == metadata["branch"]
            if metadata["branch"]
            else True
        )

        commits = get_commits_since(metadata["created"], project_path)
        result["commits_since"] = len(commits)
        result["recent_commits"] = commits[:5]

        changed = get_changed_files_since(metadata["created"], project_path)
        result["files_changed_count"] = len(changed)
        result["files_changed"] = changed[:10]
    else:
        result["current_branch"] = None
        result["branch_matches"] = True
        result["commits_since"] = 0
        result["recent_commits"] = []

        changed, truncated = get_mtime_changed_files(metadata["created"], project_path)
        result["files_changed_count"] = len(changed)
        result["files_changed"] = changed[:10]
        result["scan_truncated"] = truncated

    level, recommendation, issues = calculate_staleness_level(
        result.get("days_old") or 0,
        result["commits_since"],
        result["files_changed_count"],
        result["branch_matches"],
        len(missing),
    )

    if not is_git_repo:
        issues.append(
            "No git repository - staleness inferred from file modification times"
        )
        if result.get("scan_truncated"):
            issues.append(
                f"File scan stopped at {MAX_SCAN_FILES} files; counts are a lower bound"
            )

    result["staleness_level"] = level
    result["recommendation"] = recommendation
    result["issues"] = issues
    return result


def print_report(result: dict) -> None:
    """Print a formatted staleness report."""
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return

    bar = "=" * 62
    print(f"\n{bar}")
    print("Handoff staleness report")
    print(bar)
    print(f"File:         {result['handoff_file']}")
    print(f"Project root: {result['project_path']}")
    print(f"              ({result['project_path_source']})")
    print(f"Signal used:  {result['signal']}")

    if result["created"]:
        print(f"Created:      {result['created'].strftime('%Y-%m-%d %H:%M:%S')}")
        if result["days_old"] is not None:
            if result["days_old"] < 1:
                print(f"Age:          {result['hours_old']:.1f} hours")
            else:
                print(f"Age:          {result['days_old']:.1f} days")
    else:
        print("Created:      [not recorded in handoff]")

    print(f"\n{bar}")
    print(f"Staleness level: {result['staleness_level']}")
    print(bar)
    print(f"\nRecommendation: {result['recommendation']}")

    if result.get("issues"):
        print("\nSignals detected:")
        for issue in result["issues"]:
            print(f"  - {issue}")

    if result.get("is_git_repo"):
        print("\n--- Git status ---")
        print(f"Handoff branch: {result.get('handoff_branch') or 'unknown'}")
        print(f"Current branch: {result.get('current_branch') or 'unknown'}")
        print(f"Branch matches: {'yes' if result.get('branch_matches') else 'no'}")
        print(f"Commits since:  {result.get('commits_since', 0)}")
        print(f"Files changed:  {result.get('files_changed_count', 0)}")

        if result.get("recent_commits"):
            print("\nRecent commits:")
            for commit in result["recent_commits"]:
                print(f"  {commit}")
    else:
        print("\n--- Filesystem status ---")
        print(f"Files modified since handoff: {result.get('files_changed_count', 0)}")
        if result.get("files_changed"):
            print("\nMost relevant:")
            for f in result["files_changed"]:
                print(f"  {f}")

    if result.get("referenced_files_missing"):
        print("\nMissing referenced files:")
        for f in result["referenced_files_missing"][:5]:
            print(f"  - {f}")

    print(f"\n{bar}")
    verdicts = {
        "FRESH": "Verdict: [OK] Safe to resume",
        "SLIGHTLY_STALE": "Verdict: [OK] Review changes, then resume",
        "STALE": "Verdict: [CAUTION] Verify context before resuming",
        "VERY_STALE": "Verdict: [WARNING] Consider creating a fresh handoff",
    }
    print(verdicts.get(result["staleness_level"], "Verdict: [UNKNOWN]"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assess whether a handoff still reflects current project state."
    )
    parser.add_argument("handoff_file", help="Path to the handoff document")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON instead of a formatted report",
    )
    add_common_args(parser)
    args = parser.parse_args()

    result = check_staleness(args.handoff_file, args.project_root)

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_report(result)

    if "error" in result:
        return 2

    level = result.get("staleness_level", "UNKNOWN")
    if level in ("FRESH", "SLIGHTLY_STALE"):
        return 0
    if level == "STALE":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
