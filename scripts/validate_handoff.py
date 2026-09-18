#!/usr/bin/env python3
"""
Validate a handoff document for completeness, quality and secret exposure.

Checks performed:
    - No [TODO: ...] placeholders remain
    - Required sections present and substantive
    - Recommended sections present
    - No credentials detected
    - Referenced files resolve against the real project root
    - Composite quality score (0-100)

Usage:
    python validate_handoff.py <handoff-file> [options]

    python validate_handoff.py .handoff/2026-09-18-120000-auth.md
    python validate_handoff.py my-handoff.md --project-root /path/to/project

Options:
    --handoff-dir <path>    Override the handoff directory
    --project-root <path>   Override project root detection start point
    --json                  Emit machine-readable JSON instead of a report

Section heading levels
----------------------
Headings at levels 1 through 3 ("#", "##", "###") are all recognized as section
headers, and any of those levels terminates the preceding section. Use level 4
("####") or deeper for sub-headings that should stay inside their parent
section. The upstream skill this replaces accepted only levels 1 and 2, which
silently failed documents written with "###" and folded "###" sub-headings into
their parent section's content.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_paths import (  # noqa: E402
    ProjectRootNotFound,
    add_common_args,
    find_project_root,
)

# Heading levels treated as section boundaries: #, ## and ###.
SECTION_HEADING = r"#{1,3}"

SECRET_PATTERNS = [
    (r'["\']?[a-zA-Z_]*api[_-]?key["\']?\s*[:=]\s*["\'][^"\']{10,}["\']', "API key"),
    (r'["\']?[a-zA-Z_]*password["\']?\s*[:=]\s*["\'][^"\']+["\']', "Password"),
    (r'["\']?[a-zA-Z_]*secret["\']?\s*[:=]\s*["\'][^"\']{10,}["\']', "Secret"),
    (r'["\']?[a-zA-Z_]*token["\']?\s*[:=]\s*["\'][^"\']{20,}["\']', "Token"),
    (r'["\']?[a-zA-Z_]*private[_-]?key["\']?\s*[:=]', "Private key"),
    (r"-----BEGIN [A-Z ]+PRIVATE KEY-----", "PEM private key"),
    (r"mongodb(\+srv)?://[^/\s]+:[^@\s]+@", "MongoDB connection string with password"),
    (r"postgres(ql)?://[^/\s]+:[^@\s]+@", "PostgreSQL connection string with password"),
    (r"mysql://[^/\s]+:[^@\s]+@", "MySQL connection string with password"),
    (r"redis://[^/\s]*:[^@\s]+@", "Redis connection string with password"),
    (r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
    (r"gh[pousr]_[A-Za-z0-9]{36,}", "GitHub token"),
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI API key"),
    (r"sk-ant-[a-zA-Z0-9\-_]{20,}", "Anthropic API key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"xox[baprs]-[a-zA-Z0-9-]{10,}", "Slack token"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.", "JWT"),
]

REQUIRED_SECTIONS = [
    "Current State Summary",
    "Important Context",
    "Immediate Next Steps",
]

RECOMMENDED_SECTIONS = [
    "Architecture Overview",
    "Critical Files",
    "Files Modified",
    "Decisions Made",
    "Assumptions Made",
    "Potential Gotchas",
]

MIN_SECTION_CHARS = 50


def check_todos(content: str) -> tuple[bool, list[str]]:
    """Detect remaining TODO placeholders."""
    todos = re.findall(r"\[TODO:[^\]]*\]", content)
    return len(todos) == 0, todos


def _section_bounds(content: str, section: str) -> tuple[int, int] | None:
    """Locate a section's content range.

    Returns (start, end) character offsets of the section body, or None if the
    heading is absent. The section ends at the next heading of level 1-3, so a
    level-4 sub-heading stays inside the parent section as intended.
    """
    pattern = rf"(?:^|\n){SECTION_HEADING}\s*{re.escape(section)}\b"
    match = re.search(pattern, content, re.IGNORECASE)
    if not match:
        return None

    start = match.end()
    next_heading = re.search(rf"\n{SECTION_HEADING}\s+", content[start:])
    end = start + next_heading.start() if next_heading else len(content)
    return start, end


def check_required_sections(content: str) -> tuple[bool, list[str]]:
    """Verify required sections exist and carry substantive content."""
    missing = []
    for section in REQUIRED_SECTIONS:
        bounds = _section_bounds(content, section)
        if bounds is None:
            missing.append(f"{section} (missing)")
            continue

        body = content[bounds[0] : bounds[1]].strip()
        if "[TODO" in body:
            missing.append(f"{section} (contains TODO)")
        elif len(body) < MIN_SECTION_CHARS:
            missing.append(
                f"{section} (incomplete: {len(body)}/{MIN_SECTION_CHARS} chars)"
            )

    return len(missing) == 0, missing


def check_recommended_sections(content: str) -> list[str]:
    """Return recommended sections that are absent."""
    missing = []
    for section in RECOMMENDED_SECTIONS:
        pattern = rf"(?:^|\n){SECTION_HEADING}\s*{re.escape(section)}\b"
        if not re.search(pattern, content, re.IGNORECASE):
            missing.append(section)
    return missing


def scan_for_secrets(content: str) -> list[tuple[str, str]]:
    """Scan for credential-shaped strings."""
    findings = []
    for pattern, description in SECRET_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            findings.append((description, f"{len(matches)} potential match(es)"))
    return findings


def resolve_base_path(handoff_file: Path, override: str | None) -> tuple[Path, str]:
    """Determine the project root for verifying file references.

    The upstream skill inferred this with path.parent.parent.parent, which only
    happens to be correct for a two-level layout such as .claude/handoffs/. Any
    other depth silently produced a wrong base path and therefore wrong
    "file not found" warnings. Root detection is used instead.
    """
    if override:
        return Path(override).expanduser().resolve(), "explicit --project-root"

    try:
        root = find_project_root(handoff_file.parent)
        return root, "detected from handoff file location"
    except ProjectRootNotFound:
        return handoff_file.parent.resolve(), "fallback: handoff file directory"


def check_file_references(content: str, base_path: Path) -> tuple[list[str], list[str]]:
    """Verify that referenced project files exist."""
    patterns = [
        r"\|\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)\s*\|",
        r"`([a-zA-Z0-9_\-./]+\.[a-zA-Z]+(?::\d+)?)`",
        r"(?:^|\s)([a-zA-Z0-9_\-./]+\.[a-zA-Z]+:\d+)",
    ]

    found_files = set()
    for pattern in patterns:
        for match in re.findall(pattern, content):
            filepath = match.split(":")[0]
            if filepath and not filepath.startswith("http") and "/" in filepath:
                found_files.add(filepath)

    existing, missing = [], []
    for filepath in sorted(found_files):
        if (base_path / filepath).exists():
            existing.append(filepath)
        else:
            missing.append(filepath)

    return existing, missing


def calculate_quality_score(
    todos_clear: bool,
    missing_required: list[str],
    missing_recommended: list[str],
    secrets_found: list,
    files_missing: list[str],
) -> tuple[int, str]:
    """Compute a 0-100 quality score.

    Deductions:
        -30  TODOs remain (incomplete work; next agent lacks critical info)
        -10  per missing or incomplete required section
        -20  secrets detected (security risk; handoffs land in repos)
        -5   per unresolvable file reference, capped at -20
        -2   per missing recommended section
    """
    score = 100

    if not todos_clear:
        score -= 30
    score -= 10 * len(missing_required)
    if secrets_found:
        score -= 20
    if files_missing:
        score -= 5 * min(len(files_missing), 4)
    score -= 2 * len(missing_recommended)

    score = max(0, score)

    if score >= 90:
        rating = "Excellent - ready for handoff"
    elif score >= 70:
        rating = "Good - minor improvements suggested"
    elif score >= 50:
        rating = "Fair - needs attention before handoff"
    else:
        rating = "Poor - significant work needed"

    return score, rating


def validate_handoff(filepath: str, project_root: str | None = None) -> dict:
    """Run every validation and return a result dictionary."""
    path = Path(filepath).expanduser()

    if not path.exists():
        return {"error": f"File not found: {filepath}"}

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"Cannot read {filepath}: {exc}"}

    base_path, base_source = resolve_base_path(path, project_root)

    todos_clear, remaining_todos = check_todos(content)
    required_complete, missing_required = check_required_sections(content)
    missing_recommended = check_recommended_sections(content)
    secrets_found = scan_for_secrets(content)
    existing_files, missing_files = check_file_references(content, base_path)

    score, rating = calculate_quality_score(
        todos_clear, missing_required, missing_recommended, secrets_found, missing_files
    )

    return {
        "filepath": str(path.resolve()),
        "base_path": str(base_path),
        "base_path_source": base_source,
        "score": score,
        "rating": rating,
        "todos_clear": todos_clear,
        "remaining_todos": remaining_todos[:5],
        "todo_count": len(remaining_todos),
        "required_complete": required_complete,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "secrets_found": secrets_found,
        "files_verified": len(existing_files),
        "files_missing": missing_files[:5],
    }


def print_report(result: dict) -> bool:
    """Print a formatted report. Returns True when the handoff is ready."""
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return False

    bar = "=" * 62
    print(f"\n{bar}")
    print("Handoff validation report")
    print(bar)
    print(f"File:         {result['filepath']}")
    print(f"Project root: {result['base_path']}")
    print(f"              ({result['base_path_source']})")
    print(f"\nQuality score: {result['score']}/100 - {result['rating']}")
    print(bar)

    if result["todos_clear"]:
        print("\n[PASS] No TODO placeholders remaining")
    else:
        print(f"\n[FAIL] {result['todo_count']} TODO placeholder(s) found:")
        for todo in result["remaining_todos"]:
            print(f"       - {todo[:60]}")

    if result["required_complete"]:
        print("\n[PASS] All required sections complete")
    else:
        print("\n[FAIL] Missing or incomplete required sections:")
        for section in result["missing_required"]:
            print(f"       - {section}")
        print("       Note: section headings must be level 1-3 (#, ##, ###).")

    if not result["secrets_found"]:
        print("\n[PASS] No potential secrets detected")
    else:
        print("\n[WARN] Potential secrets detected:")
        for secret_type, detail in result["secrets_found"]:
            print(f"       - {secret_type}: {detail}")

    if result["files_missing"]:
        print(f"\n[WARN] {len(result['files_missing'])} referenced file(s) not found:")
        for f in result["files_missing"]:
            print(f"       - {f}")
    else:
        print(f"\n[INFO] {result['files_verified']} file reference(s) verified")

    if result["missing_recommended"]:
        print("\n[INFO] Consider adding these sections:")
        for section in result["missing_recommended"]:
            print(f"       - {section}")

    print(f"\n{bar}")

    if result["secrets_found"]:
        print("Verdict: BLOCKED - remove secrets before handoff")
        return False
    if result["score"] >= 70:
        print("Verdict: READY for handoff")
        return True
    print("Verdict: NEEDS WORK - complete the required sections")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a handoff document for completeness and security."
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

    result = validate_handoff(args.handoff_file, args.project_root)

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("score", 0) >= 70 and not result.get(
            "secrets_found"
        ) else 1

    return 0 if print_report(result) else 1


if __name__ == "__main__":
    sys.exit(main())
