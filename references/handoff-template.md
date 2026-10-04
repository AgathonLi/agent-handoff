# Compact handoff template

`create_handoff.py` generates metadata, lineage and three required sections.
Each required section needs at least 50 substantive characters. Fill them with
information the successor needs, not prose to satisfy a score.

```markdown
# Handoff: <task and transfer boundary>

## Session Metadata

- Created: <YYYY-MM-DD HH:MM:SS>
- Project: <project path>
- Branch: <branch or non-Git>

## Handoff Chain

- Continues from: <link or None; lineage only, read on demand>

## Current State Summary

Verified outcome and unfinished work, with evidence pointers. Distinguish local,
committed and deployed status. List relevant changes here or link an existing
report; do not recreate the whole project history.

## Important Context

Authorization boundaries, active blockers, new decisions and their rationale.
Point at stable architecture/contracts. Mark assumptions and how to verify them.

## Immediate Next Steps

First concrete action, its prerequisites and verification. Confirm it is still
pending. If there is no remaining work, say so and do not invent a task list.
```

## Optional sections

Add `Critical Files`, `Decisions Made`, `Files Modified`, `Potential Gotchas`,
`Assumptions Made` or `Architecture Overview` only when they add needed context.
Their absence costs 2 points each under the existing scoring scheme; a complete
three-section handoff normally scores 88 and is acceptable. Do not pursue 100.
Legacy long handoffs remain supported; no migration is necessary.

## Before finalizing

- Re-check pending work, blockers and the first action against current evidence.
- Keep sustained state in the project's fact source, not in several snapshots.
- Replace the title and all TODOs. Validate once; rerun only after editing.
  Required checks pass, no detected credentials, score at least 70. This does
  not prove factual accuracy.
- Follow project storage/Git policy; do not force-add ignored handoffs, commit
  automatically or infer that staging delivers the file to another device.

## Formatting

Section headings are levels 1–3; subheadings inside sections are level 4+.
Headings and comments inside fenced code do not define document sections.
For a file that genuinely does not yet exist, write `src/auth.py` `(planned)`
(two separate backtick spans). Remove the exemption after creation.
Never include secrets or actual credential values. Detection covers limited
patterns, so a clean validator result is not a guarantee of safe disclosure.
