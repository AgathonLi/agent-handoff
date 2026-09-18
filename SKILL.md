---
name: agent-handoff
description: "Host-neutral session handoff documents for cross-agent development. Creates, validates, lists and freshness-checks handoff files that any coding agent can read - Claude Code, Codex, WorkBuddy, Hermes, Zcode, Cursor, OpenCode. Triggered when: (1) user requests handoff/context save/state save, (2) context window approaches capacity, (3) a task milestone completes, (4) a work session ends, (5) user says 'create handoff', 'save state', 'I need to pause', 'context is getting full', 'hand this to Codex', 'take this to another agent', (6) resuming with 'load handoff', 'resume from', 'continue where we left off'. Storage directory is configurable via --handoff-dir, HANDOFF_DIR or .handoffrc; defaults to the host-neutral .handoff/ directory rather than any single client's config namespace."
agent_created: true
---

# Agent handoff

Creates handoff documents that let a fresh agent continue work with no
ambiguity, and keeps those documents readable by every agent in the rotation
rather than only the one that wrote them.

## Why the directory is host-neutral

A handoff document has exactly one job: be found and read by whoever picks the
work up next. Storing it inside a single client's configuration namespace
(`.claude/`, `.workbuddy/`, `.cursor/`) defeats that job — the other agents never
look there. This skill therefore defaults to `.handoff/` at the project root,
which belongs to the project rather than to any client.

Do not "fix" a wrong path by swapping one client namespace for another. If the
path needs to change, change it through the resolution chain below.

## Directory resolution

The handoff directory is resolved by `scripts/handoff_paths.py`. First match
wins; every level works independently of the ones above it.

| Level | Source | Notes |
|-------|--------|-------|
| 1 | `--handoff-dir <path>` | Highest priority. Relative paths resolve against the project root |
| 2 | `HANDOFF_DIR` env var | For session-wide or host-level injection |
| 3 | `.handoffrc` at project root | Per-project, travels with the repository |
| 4 | An existing known layout | Preserves established conventions, migrates nothing |
| 5 | `<project root>/.handoff/` | Host-neutral default |

Level 4 probes these layouts in order and adopts the first one that already
exists: `.handoff/`, `.agent/handoffs/`, `.workbuddy/handoffs/`,
`.claude/handoffs/`, `thoughts/shared/handoffs/`. A project already using one of
them keeps using it; no files are moved.

`.handoffrc` accepts either form:

```
.handoff
```

```
handoff_dir = docs/handoffs
```

Every script prints which level decided the outcome. Read that line before
assuming a path is wrong.

## Project root detection

Scripts locate the project root by walking upward from the current directory
looking for `.git`, `.handoffrc`, `AGENTS.md`, `CLAUDE.md`, `package.json`,
`pyproject.toml` or similar markers.

If no marker is found, the scripts **fail with an error** instead of writing into
the current directory. Silent fallback to the working directory is what causes
handoff files to appear inside unrelated directories — including inside this
skill's own directory when a script is run from there. Use `--project-root` or
`--handoff-dir` to resolve such a failure.

## CREATE workflow

### Step 1: generate the scaffold

```bash
python scripts/create_handoff.py [slug]
python scripts/create_handoff.py implementing-auth
python scripts/create_handoff.py auth-part-2 --continues-from 2026-09-18-auth.md
python scripts/create_handoff.py my-task --handoff-dir docs/handoffs
```

The script resolves the directory, reports the precedence level used, pre-fills
timestamp, project path, git branch, recent commits and modified files, then
leaves `[TODO: ...]` markers for everything only the outgoing agent knows.

### Step 2: complete the document

Fill in every `[TODO: ...]` marker. Prioritize in this order:

1. **Important Context** — what the next agent MUST know
2. **Immediate Next Steps** — concrete, actionable first moves
3. **Current State Summary** — where things stand right now
4. **Decisions Made** — choices *with rationale*, not just outcomes

Rationale matters more than outcome. Without the reasoning, the next agent
re-litigates settled decisions or repeats a rejected approach.

### Step 3: validate

```bash
python scripts/validate_handoff.py <handoff-file>
python scripts/validate_handoff.py <handoff-file> --json
```

Checks: no remaining TODOs, required sections present and substantive, no
credentials, referenced files resolve, quality score 0-100.

Do not finalize a handoff with secrets detected or a score below 70.

### Step 4: confirm

Report the file location, score, any warnings, and the first action item for the
next session.

## RESUME workflow

### Step 1: find handoffs

```bash
python scripts/list_handoffs.py
python scripts/list_handoffs.py --project-root /path/to/project
```

### Step 2: check freshness

```bash
python scripts/check_staleness.py <handoff-file>
```

Levels: `FRESH` (resume safely), `SLIGHTLY_STALE` (review first), `STALE`
(verify carefully), `VERY_STALE` (create a fresh handoff instead).

Git history is the strongest signal. For projects without version control the
check falls back to file modification times rather than giving up, and the report
names which signal was used.

### Step 3: read the document fully

Read the whole handoff before acting. If it has a "Continues from" link, read the
linked predecessor too.

### Step 4: verify context

Follow [references/resume-checklist.md](references/resume-checklist.md): confirm
the project directory and branch, check whether blockers were resolved, validate
that assumptions still hold, review modified files for conflicts.

### Step 5: begin work

Start at "Immediate Next Steps" item 1. Consult "Critical Files", "Key Patterns
Discovered" and "Potential Gotchas" as you go.

## Section heading levels

**Required and recommended section headings must be level 1, 2 or 3** — `#`,
`##` or `###`. Level 2 (`##`) is what the generated scaffold uses; keep it.

For sub-headings *inside* a section, use level 4 (`####`) or deeper. Any heading
at level 1-3 terminates the preceding section, so a level-3 sub-heading would cut
its parent section short and the parent could then fail the 50-character minimum
content check.

Required sections, each needing at least 50 characters of real content:
`Current State Summary`, `Important Context`, `Immediate Next Steps`.

## Handoff chaining

For long-running work, chain handoffs to preserve lineage:

```
handoff-1.md
    ↓  --continues-from handoff-1.md
handoff-2.md
    ↓  --continues-from handoff-2.md
handoff-3.md
```

Read the most recent first, then walk back as needed.

## Cross-agent use

The point of the neutral directory is that handoffs survive an agent switch. To
make them easy to find, add a line to the project's `AGENTS.md`:

```markdown
## Handoffs

Session handoff documents live in `.handoff/`. Read the most recent one before
starting work; write a new one before finishing.
```

`AGENTS.md` is read natively by Codex and OpenCode, and by Claude Code when
pointed at it. That one line plus a neutral directory is what makes the handoff
actually reachable from another agent.

## Resources

### scripts/

| Script | Purpose |
|--------|---------|
| `handoff_paths.py` | Shared directory and project root resolution. Imported by the others; not run directly |
| `create_handoff.py [slug] [--continues-from F] [--handoff-dir D] [--project-root R]` | Generate a scaffolded handoff |
| `list_handoffs.py [--handoff-dir D] [--project-root R] [--json]` | List available handoffs |
| `validate_handoff.py <file> [--project-root R] [--json]` | Check completeness, quality and secrets |
| `check_staleness.py <file> [--project-root R] [--json]` | Assess whether context is still current |

All scripts accept `--handoff-dir` and `--project-root`. Validation and
staleness also accept `--json` for programmatic use.

`sync_to_host.py` exists only in the development repository and is not part of an
installed copy. It pushes the repository to the host skill directories and
deliberately withholds `AGENTS.md`, `tests/` and `.github/`: `AGENTS.md` is a
project-root marker, so copying it into an installed skill directory would make
that directory look like a project root and send handoff files there instead of
raising an error.

### references/

- [handoff-template.md](references/handoff-template.md) — full template with guidance
- [resume-checklist.md](references/resume-checklist.md) — verification checklist for resuming agents
