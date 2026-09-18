# Handoff template

Reference structure for handoff documents. `create_handoff.py` pre-fills the
metadata sections; you complete the rest.

## Heading level rules

- Section headings: level 1, 2 or 3 (`#`, `##`, `###`). The scaffold uses `##`.
- Sub-headings inside a section: level 4 (`####`) or deeper.

A heading at level 1-3 terminates the preceding section. Using `###` for a
sub-heading cuts its parent section short, which can push the parent below the
50-character minimum and fail validation.

## Required sections

Each needs at least 50 characters of substantive content:

- `Current State Summary`
- `Important Context`
- `Immediate Next Steps`

## Recommended sections

Each absent section costs 2 points on the quality score:

- `Architecture Overview`
- `Critical Files`
- `Files Modified`
- `Decisions Made`
- `Assumptions Made`
- `Potential Gotchas`

---

# Handoff: [TASK_TITLE]

## Session Metadata

- Created: [TIMESTAMP]
- Project: [PROJECT_PATH]
- Branch: [GIT_BRANCH]
- Session duration: [APPROX_DURATION]

Recent commits for context:

  - [commit line]

## Handoff Chain

- **Continues from**: None (fresh start)
- **Supersedes**: None

## Current State Summary

One paragraph: what was being worked on, current status, where things left off.
Be concrete. "Refactoring the auth module" is not useful; "Extracted token
validation into `auth/tokens.py`; the refresh path still calls the old helper and
needs migrating" is.

## Architecture Overview

Structural insights discovered this session — main components, data flow, module
boundaries. Record what took effort to figure out, not what is obvious from the
directory listing.

## Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| path/to/file | What it does | Why it matters for this task |

## Key Patterns Discovered

Conventions and idioms the next agent should follow. Include the ones that are
not self-evident — error handling style, naming rules, test layout, places where
the codebase deliberately deviates from convention.

## Tasks Finished

- [x] Task 1 — what was done
- [x] Task 2 — what was done

## Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
| path/to/file | What changed | Why |

## Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Chose X over Y | X, Y, Z | Why X won |

Record rejected options and the reason for rejection. Without them the next
agent re-proposes the same wrong approach.

## Immediate Next Steps

1. Most critical next action — specific enough to start immediately
2. Second priority
3. Third priority

## Blockers and Open Questions

- [ ] Blocker: [description] — needs: [what unblocks it]
- [ ] Question: [unclear point] — suggested: [possible resolution]

## Deferred Items

- Item (deferred because: [reason])

## Important Context

The most important section. Critical information the next agent MUST know:
non-obvious constraints, things that look broken but are intentional, approaches
already tried and abandoned, user preferences established this session.

Write this as if the reader has no access to the conversation. They do not.

## Assumptions Made

- Assumption: [what was taken as true] — verify by: [how to confirm]

## Potential Gotchas

- Edge cases, quirks, non-obvious behaviour that could trip up a new agent

## Environment State

Tools and services in use, any running processes or dev servers, and the NAMES of
relevant environment variables.

Never record variable values. The validator scans for credentials and will block
the handoff.

## Related Resources

- Relevant documentation
- Related file paths
- External resources consulted

---

## Usage notes

1. Be specific. Vague descriptions do not help the next agent.
2. Include line numbers where useful: `src/auth.ts:142`.
3. Prioritize `Important Context` and `Immediate Next Steps`.
4. Never include secrets — keys, passwords, tokens, connection strings.
5. Record WHY alongside WHAT. Rationale is the part that cannot be recovered
   from reading the diff.
