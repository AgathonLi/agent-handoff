#!/usr/bin/env python3
"""
Shared path resolution for agent-handoff.

This module is the single source of truth for two questions every script needs
answered:

    1. Where is the project root?
    2. Where do handoff documents live?

Both answers are computed here, never hardcoded in the calling scripts, and
never inferred by counting parent directories.

Project root resolution
-----------------------
Walks upward from a starting directory looking for a root marker. If no marker
is found, resolution FAILS rather than silently falling back to the current
working directory. Silent fallback is what causes handoff files to be written
into unrelated directories (for example into the skill's own directory when a
script is invoked from there).

Handoff directory resolution (first match wins)
----------------------------------------------
    1. Explicit CLI argument       --handoff-dir <path>
    2. Environment variable        HANDOFF_DIR
    3. Project config file         .handoffrc  (at project root)
    4. Existing directory probe    any known layout already present
    5. Host-neutral default        <project root>/.handoff

Every level works independently of the levels above it. A project that already
stores handoffs somewhere unusual keeps working via level 3 or 4 with no
migration.

Design note on the default
--------------------------
The default is deliberately NOT inside a client-specific namespace such as
.claude/ or .workbuddy/. Handoff documents belong to the project and must be
discoverable by whichever agent picks the work up next. Putting them inside one
client's configuration namespace makes them invisible to every other client,
which defeats the purpose of writing them.
"""

from __future__ import annotations

import os
from pathlib import Path

# Host-neutral default. Readable by any agent, owned by no client.
DEFAULT_HANDOFF_DIRNAME = ".handoff"

# Config file consulted at the project root.
CONFIG_FILENAME = ".handoffrc"

# Environment variable override.
ENV_VAR = "HANDOFF_DIR"

# Markers that identify a project root, in priority order. A version control
# directory is the strongest signal; agent instruction files and package
# manifests cover projects without version control.
ROOT_MARKERS = [
    ".git",
    ".hg",
    ".svn",
    CONFIG_FILENAME,
    "AGENTS.md",
    "CLAUDE.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
]

# Directory layouts that may already hold handoffs. Probed in priority order
# so that an existing convention is preserved instead of being replaced.
KNOWN_LAYOUTS = [
    ".handoff",
    os.path.join(".agent", "handoffs"),
    os.path.join(".workbuddy", "handoffs"),
    os.path.join(".claude", "handoffs"),
    os.path.join("thoughts", "shared", "handoffs"),
]


class ProjectRootNotFound(Exception):
    """Raised when no project root marker can be located.

    Callers should surface this to the user rather than defaulting to the
    current working directory. Writing a handoff into an arbitrary directory is
    worse than refusing to write one.
    """


def find_project_root(start: str | os.PathLike[str] | None = None) -> Path:
    """Walk upward from `start` until a root marker is found.

    Args:
        start: Directory to begin from. Defaults to the current working
            directory.

    Returns:
        Absolute path to the project root.

    Raises:
        ProjectRootNotFound: If the filesystem root is reached without finding
            any marker.
    """
    current = Path(start).resolve() if start else Path.cwd().resolve()

    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        for marker in ROOT_MARKERS:
            if (candidate / marker).exists():
                return candidate

    raise ProjectRootNotFound(
        f"No project root marker found at or above: {current}\n"
        f"Looked for: {', '.join(ROOT_MARKERS[:6])}, ...\n\n"
        f"Fix by either:\n"
        f"  - running the command from inside a project, or\n"
        f"  - creating a {CONFIG_FILENAME} file at the project root, or\n"
        f"  - passing --handoff-dir <path> explicitly."
    )


def read_config(project_root: Path) -> str | None:
    """Read the handoff directory from the project config file.

    The config format is intentionally minimal. Either of these works:

        .handoff

    or:

        handoff_dir = .handoff

    Blank lines and lines beginning with '#' are ignored. The first usable line
    wins.

    Returns:
        The configured directory as written, or None if absent or empty.
    """
    config_path = project_root / CONFIG_FILENAME
    if not config_path.is_file():
        return None

    try:
        raw = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if key.strip() in ("handoff_dir", "dir", "path"):
                value = value.strip().strip("\"'")
                if value:
                    return value
            continue
        return line.strip("\"'")

    return None


def probe_existing_layout(project_root: Path) -> str | None:
    """Return the first known layout that already exists in the project.

    This preserves established conventions. A project already using
    .workbuddy/handoffs/ keeps using it; no migration is triggered and no files
    are moved.

    Returns:
        The relative layout path, or None if no known layout is present.
    """
    for layout in KNOWN_LAYOUTS:
        if (project_root / layout).is_dir():
            return layout
    return None


def resolve_handoff_dir(
    explicit: str | None = None,
    start: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> tuple[Path, Path, str]:
    """Resolve the handoff directory using the full precedence chain.

    Args:
        explicit: Value of --handoff-dir, if the caller passed one.
        start: Directory to begin root detection from. Defaults to cwd.
        create: Whether to create the directory if it does not exist.

    Returns:
        A tuple of (handoff_dir, project_root, source) where `source` names the
        precedence level that decided the outcome. Report `source` to the user
        so the resolution is never a black box.

    Raises:
        ProjectRootNotFound: If the project root cannot be determined and
            `explicit` was not an absolute path.
    """
    # Level 1: explicit CLI argument.
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_absolute():
            # An absolute override does not require root detection to succeed,
            # but we still try so that git metadata can be gathered.
            try:
                project_root = find_project_root(start)
            except ProjectRootNotFound:
                project_root = candidate.parent
            resolved = candidate
        else:
            project_root = find_project_root(start)
            resolved = project_root / candidate
        return _finalize(resolved, project_root, "--handoff-dir argument", create)

    # Levels 2-5 all require a known project root.
    project_root = find_project_root(start)

    # Level 2: environment variable.
    env_value = os.environ.get(ENV_VAR, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        resolved = candidate if candidate.is_absolute() else project_root / candidate
        return _finalize(resolved, project_root, f"{ENV_VAR} environment variable", create)

    # Level 3: project config file.
    configured = read_config(project_root)
    if configured:
        candidate = Path(configured).expanduser()
        resolved = candidate if candidate.is_absolute() else project_root / candidate
        return _finalize(resolved, project_root, f"{CONFIG_FILENAME} config file", create)

    # Level 4: an existing layout already in use.
    existing = probe_existing_layout(project_root)
    if existing:
        return _finalize(
            project_root / existing, project_root, f"existing directory ({existing})", create
        )

    # Level 5: host-neutral default.
    return _finalize(
        project_root / DEFAULT_HANDOFF_DIRNAME,
        project_root,
        f"default ({DEFAULT_HANDOFF_DIRNAME})",
        create,
    )


def _finalize(
    handoff_dir: Path, project_root: Path, source: str, create: bool
) -> tuple[Path, Path, str]:
    """Normalize the resolved paths and optionally create the directory."""
    handoff_dir = handoff_dir.resolve()
    project_root = Path(project_root).resolve()
    if create:
        handoff_dir.mkdir(parents=True, exist_ok=True)
    return handoff_dir, project_root, source


def add_common_args(parser) -> None:
    """Register the shared --handoff-dir / --project-root arguments.

    Every entry point accepts the same overrides so behaviour is uniform.
    """
    parser.add_argument(
        "--handoff-dir",
        dest="handoff_dir",
        default=None,
        metavar="PATH",
        help=(
            "Directory holding handoff documents. Overrides all other sources. "
            "Relative paths resolve against the project root."
        ),
    )
    parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        metavar="PATH",
        help=(
            "Start directory for project root detection. "
            "Defaults to the current working directory."
        ),
    )
