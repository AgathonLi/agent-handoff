# agent-handoff

[![tests](https://github.com/AgathonLi/agent-handoff/actions/workflows/test.yml/badge.svg)](https://github.com/AgathonLi/agent-handoff/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Host-neutral session handoff documents for cross-agent development.

Write a handoff in one agent, resume from it in another. Works with Claude Code,
Codex, WorkBuddy, Cursor, OpenCode, Zed and anything else that can read a
Markdown file and run Python.

## The problem this solves

Most handoff tooling stores its documents inside one client's configuration
namespace — `.claude/handoffs/`, `.cursor/`, or similar. That is fine until you
switch agents, at which point the handoff becomes invisible to the agent that
needs it most. The document had exactly one job, and the storage location
defeated it.

`agent-handoff` defaults to `.handoff/` at the project root: a directory that
belongs to the project rather than to any client, and that every agent can find.
The location is configurable through five independent precedence levels, so
existing conventions keep working without migration.

## Install

Requires Python 3.10+. No third-party dependencies.

Clone into your agent's skills directory:

```bash
# Claude Code
git clone https://github.com/AgathonLi/agent-handoff ~/.claude/skills/agent-handoff

# WorkBuddy
git clone https://github.com/AgathonLi/agent-handoff ~/.workbuddy/skills/agent-handoff

# OpenCode / Codex (agent-compatible path)
git clone https://github.com/AgathonLi/agent-handoff ~/.agents/skills/agent-handoff
```

Or use the scripts standalone, with no skill host at all:

```bash
git clone https://github.com/AgathonLi/agent-handoff
python agent-handoff/scripts/create_handoff.py my-task
```

## Usage

```bash
# Create
python scripts/create_handoff.py implementing-auth

# Create, chained to a previous handoff
python scripts/create_handoff.py auth-part-2 --continues-from 2026-09-18-auth.md

# List
python scripts/list_handoffs.py

# Validate before finishing
python scripts/validate_handoff.py .handoff/2026-09-18-120000-auth.md

# Check freshness before resuming
python scripts/check_staleness.py .handoff/2026-09-18-120000-auth.md
```

Every script accepts `--handoff-dir` and `--project-root`. `validate_handoff.py`,
`list_handoffs.py` and `check_staleness.py` also accept `--json`.

## Directory resolution

First match wins. Each level works independently of the ones above it.

| Level | Source | Notes |
|-------|--------|-------|
| 1 | `--handoff-dir <path>` | Highest priority |
| 2 | `HANDOFF_DIR` env var | Session or host-level injection |
| 3 | `.handoffrc` at project root | Per-project, travels with the repo |
| 4 | An existing known layout | Adopts current conventions, migrates nothing |
| 5 | `<project root>/.handoff/` | Host-neutral default |

Level 4 probes `.handoff/`, `.agent/handoffs/`, `.workbuddy/handoffs/`,
`.claude/handoffs/` and `thoughts/shared/handoffs/` in that order. A project
already using any of them keeps using it — no files are moved.

Every command prints which level decided the outcome:

```
Project root:  /path/to/project
Handoff dir:   /path/to/project/.handoff
Resolved via:  default (.handoff)
```

`.handoffrc` accepts either form:

```
.handoff
```

```
handoff_dir = docs/handoffs
```

## Project root detection

Scripts walk upward looking for `.git`, `.handoffrc`, `AGENTS.md`, `CLAUDE.md`,
`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod` and similar markers.

**If no marker is found, the scripts fail instead of writing into the current
directory.** Silent fallback to `cwd` is how handoff files end up in unrelated
places — including inside the skill's own directory when a script is invoked from
there. Pass `--project-root` or `--handoff-dir` to resolve such a failure.

## Section heading levels

Section headings must be level 1, 2 or 3 (`#`, `##`, `###`). The generated
scaffold uses `##`.

For sub-headings *inside* a section, use level 4 (`####`) or deeper. Any heading
at level 1-3 terminates the preceding section, so a level-3 sub-heading would cut
its parent short and the parent could then fail the 50-character minimum content
check.

Required sections, each needing at least 50 characters of real content:

- `Current State Summary`
- `Important Context`
- `Immediate Next Steps`

## Validation

`validate_handoff.py` scores 0-100 and blocks on credentials.

| Check | Deduction |
|-------|-----------|
| `[TODO: ...]` placeholders remain | -30 |
| Missing or incomplete required section | -10 each |
| Credentials detected | -20, and verdict is BLOCKED |
| Referenced file does not resolve | -5 each, capped at -20 |
| Missing recommended section | -2 each |

Secret patterns cover API keys, passwords, bearer tokens, JWTs, PEM private keys,
database connection strings with embedded passwords, and provider-specific
formats for AWS, GitHub, OpenAI, Anthropic, Google and Slack.

A handoff with secrets detected is BLOCKED regardless of score.

## Staleness

`check_staleness.py` returns `FRESH`, `SLIGHTLY_STALE`, `STALE` or `VERY_STALE`
based on age, commits since the handoff, files changed, branch divergence, and
referenced files that no longer exist.

Git history is the strongest signal. For projects without version control the
check falls back to filesystem modification times rather than giving up, and the
report names which signal was used.

Exit codes: `0` fresh or slightly stale, `1` stale, `2` very stale or resolution
failure.

## Cross-agent discoverability

A neutral directory is necessary but not sufficient — the next agent still has to
know to look. Add this to the project's `AGENTS.md`:

```markdown
## Handoffs

Session handoff documents live in `.handoff/`. Read the most recent one before
starting work; write a new one before finishing.
```

`AGENTS.md` is read natively by Codex and OpenCode, and by Claude Code when
pointed at it. That one line plus a neutral directory is what makes a handoff
actually reachable from another agent.

## Development

```bash
python tests/test_agent_handoff.py
```

No third-party dependencies. CI runs the suite on Linux, Windows and macOS
against Python 3.10 and 3.13.

If you develop in a clone and also keep installed copies under
`~/.workbuddy/skills/`, `~/.claude/skills/` or `~/.agents/skills/`, push changes
outward with:

```bash
python scripts/sync_to_host.py            # dry run
python scripts/sync_to_host.py --apply
```

The sync is one-way and withholds `AGENTS.md`, `tests/`, `.github/` and itself.
Withholding `AGENTS.md` is a correctness requirement rather than housekeeping:
it is a project-root marker, so an installed copy containing it would register as
a project root and receive handoff files instead of raising an error.

## Relationship to prior work

This is an independent implementation, written against the same problem as
several existing handoff tools but not derived from any of them. The behavioural
differences that motivated it:

- Storage directory is host-neutral and configurable, rather than fixed inside
  one client's namespace.
- Project root is detected from markers, not inferred by counting parent
  directories. Depth-counting silently produces a wrong root whenever the handoff
  directory depth differs from the layout assumed.
- Missing project root is an error, not a silent write to `cwd`.
- Heading levels 1-3 are all recognized, and the requirement is documented.
- Non-git projects get a filesystem-based staleness verdict instead of `UNKNOWN`.

## License

MIT
