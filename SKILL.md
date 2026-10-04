---
name: agent-handoff
description: "Create, locate, validate and freshness-check host-neutral session handoffs. Use for 'create handoff', 'save state', 'I need to pause', 'context is getting full', 'hand this to Codex' or another agent, 'load handoff', 'resume from' and 'continue where we left off'. Create only for requested handoffs or meaningful work at a pause, transfer or imminent context-loss boundary; locating or resuming does not create a new document."
agent_created: true
---

# Agent handoff

Create short, host-neutral Markdown snapshots so another agent can continue.
Requires Python 3.10+, no third-party dependencies. Handoffs are snapshots, not
project state authorities, task managers or authorization grants.

## When to use

- The user requests a handoff, save state, pause or transfer to another agent.
- Context is about to be lost and meaningful work needs to continue.
- A session genuinely ends with unfinished work or new context a successor needs.
- Resume or locate a previous handoff, or validate an existing document.

Do not automatically create one for a read-only query, every small milestone,
or every message ending. Continuous work by the same agent does not need a new
handoff at each test, commit or push. Existing project rules and explicit user
requests take precedence; do not silently rewrite their handoff policy.

## Directory resolution

All directory decisions go through `scripts/handoff_paths.py`, first match wins:

1. `--handoff-dir <path>` (relative paths resolve against the project root).
2. `HANDOFF_DIR` environment variable.
3. Project-root `.handoffrc`: bare path, or `handoff_dir = docs/handoffs`.
4. Existing `.handoff/`, `.agent/handoffs/`, `.workbuddy/handoffs/`,
   `.claude/handoffs/`, `thoughts/shared/handoffs/`, in that order.
5. `<project root>/.handoff/`, the host-neutral default.

Each script reports the winning level. Existing layouts are adopted, never
migrated automatically. Do not swap one client's namespace for another.
Project-root detection walks upward for `.git`, `.handoffrc`, `AGENTS.md`,
`CLAUDE.md`, `package.json`, `pyproject.toml` and similar markers. Creation fails
with exit 2 when no root can be detected; it must never silently write into cwd.
Run from the target project, or pass `--project-root` explicitly.

## Intent and commands

Skill invocation is natural-language intent, not script argv. Skill `args` are
not forwarded to scripts; there is no `--dir` flag. Pick the script, then pass
flags on its command line. Use the host's terminal tool to execute:

```bash
# Locate/read only: default shows newest 5; creates nothing
python scripts/list_handoffs.py --project-root /path/to/project
python scripts/list_handoffs.py --limit 1
python scripts/list_handoffs.py --all

# Create only when there is a real transfer boundary
python scripts/create_handoff.py my-task
python scripts/create_handoff.py next-stage --continues-from previous.md

# Validate a completed document
python scripts/validate_handoff.py <handoff-file>

# Check an older document, or when listing reports unknown freshness
python scripts/check_staleness.py <handoff-file>
```

All scripts accept `--handoff-dir` and `--project-root`; list, validate and
check also accept `--json`. List JSON reports total `count`, `shown_count`,
`hidden_count` and only the selected `handoffs`; use `--all` for a full inventory.

## Create

1. Generate the compact scaffold: metadata, lineage and three core sections.
2. Replace the title and all TODOs. Each required section needs at least 50
   substantive characters:
   - **Current State Summary**: verified outcome, unfinished work, relevant
     changes and evidence pointers. Distinguish local, committed and deployed.
   - **Important Context**: authorization boundaries, blockers, new decisions
     with rationale and assumptions that need verification.
   - **Immediate Next Steps**: the first concrete action, prerequisites and
     verification. If nothing remains, say so rather than inventing tasks.
3. Add optional sections only when they carry useful new information. Link
   stable architecture, contracts and environment notes in project documents;
   do not repeat them or fill irrelevant sections just to earn points.
4. Before validating, re-check **pending work, blockers and first action**
   against the current fact source or evidence. Remove resolved items; do not
   copy yesterday's todo list. Observations and unverified assumptions differ.
5. Validate once after completing the document, again only if it changes.
   Required sections must pass, the scaffold title must be replaced, no TODOs
   or detected credentials may remain, and score must be at least 70.
   A three-section document normally scores 88;
   100 is not a goal. Scores are structural/static signals, not factual proof.
6. Report the path, score, warnings and next action. Save according to project
   policy: Git-tracked handoffs may be staged precisely when permitted; ignored
   handoffs must not be force-added. No automatic commit or push. Staging is
   not a backup or proof of cross-device delivery. Respect existing approved
   local/sync policies; do not invent a new backup workflow.

If an unused scaffold will not be completed, remove only that newly created
file in the same turn, subject to the user's write policy. Listing reports
incomplete documents; only untitled scaffolds get conditional removal hints.
Titled drafts get a completion reminder. Listing never deletes anything itself.

Plans and reviews do not need a new document kind or special validator. Keep
formal plans/reviews in their established project home; handoffs point to them.

## Resume

1. List recent handoffs and choose the **latest relevant** one, not blindly the
   newest file from an unrelated task. Listing checks freshness of the newest
   file only; run the separate check for another file or an unknown result.
2. Read the selected handoff fully. A `Continues from` link is lineage: follow
   it only for missing rationale, unresolved ambiguity or historical evidence.
   Do not automatically load the entire chain.
3. Verify the project/branch and the next action's prerequisites. Follow the
   task-relevant parts of [resume-checklist.md](references/resume-checklist.md).
   Current observed state and designated fact sources override old snapshots;
   conflicting sources must be surfaced before state-changing work.
4. Begin the first still-valid action under current user authorization. A stale
   document alone is not a reason to write a replacement before doing work.

`FRESH` means no obvious stale signals were found, not that the text is correct
or execution is safe. Git checks use history; non-Git checks use modification
times, skip generated `outputs/`, `tmp/`, dependencies and client state, and
report scan truncation. Those skipped artifacts may still matter to a task;
verify the cited evidence directly. Freshness does not inspect live services.

## History and project pointers

Keep history in place by default. File accumulation is not itself a runtime
fault. Default listing limits output, not retention. Do not add automatic
archive/delete jobs, telemetry, indexes or lifecycle databases.
Only propose manual archival for completed work whose lasting decisions are
already in the fact source and whose history no active handoff depends on.
Moving files requires approval and link checks; list reads top-level `*.md` only.

Suggested project `AGENTS.md` pointer (adapt to its existing policy):

```markdown
## Handoffs

Snapshots live in `.handoff/`, not the project state authority. Read the latest
relevant handoff when resuming. Write a short one when pausing or transferring
meaningful work; follow project storage/Git policy. Verify pending items first.
```

Update an existing index or memory pointer only when it would otherwise become
wrong. Do not duplicate current state and pending work into several documents.

## Formatting and limitations

Section headings use levels 1–3; subheadings within sections use level 4+.
Outside fenced code, higher-level subheadings terminate the parent and can fail
its content minimum. Headings and comments inside code fences are not sections.
For genuinely future files, use `src/auth.py` `(planned)` (two separate backtick
spans). Remove the exemption when the file exists. External runtime paths can
produce false missing-reference warnings; prefer an accurate project-doc pointer.
A validator checks limited patterns, not all secrets or all references; its score
cannot verify authority, live state, semantic consistency or completeness.

## Development resources

- [handoff-template.md](references/handoff-template.md): compact authoring guide.
- [resume-checklist.md](references/resume-checklist.md): proportional verification.
- `scripts/sync_to_host.py` is development-only, one-way source → installed copy.
  It excludes root markers, tests, reviews and local state; preserve host metadata.
  Installed copies are not an alternative source of truth.
