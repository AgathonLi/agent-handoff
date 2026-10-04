# Proportional resume checklist

Apply the checks relevant to the next action, not a new full-project audit.

## Locate and read

- List recent handoffs; choose the latest relevant task, not just the newest file.
- Use listing freshness for the newest file. Run `check_staleness.py` only for
  another file or an unknown assessment; no duplicate freshness check is needed.
- Confirm project root and branch (where applicable); understand device-path
  differences rather than requiring a Windows path to exist on Linux.
- Read the selected document fully. Follow predecessor links only for missing
  rationale, ambiguity or evidence; do not load the entire chain automatically.

## Verify the first action

- Is the task still pending, or already resolved in the current fact source?
- Do its relevant files and evidence exist, and do assumptions still hold?
- Is the observed working state consistent with the proposed change? Check
  branch/status/diff where Git is available; do not overwrite concurrent work.
- Are blockers still active, and is authorization current for this action?
- For live-data or deployed-state claims, check the actual source when relevant;
  neither snapshot age nor validator score proves them.

`FRESH` means no obvious stale signals found, not safe execution. `VERY_STALE`
means carefully reconstruct current premises, not automatically create another
handoff. Non-Git scans ignore generated outputs and tmp; inspect task evidence
there directly rather than interpreting ignored files as verified unchanged.

## Begin or surface a conflict

Start the first still-valid authorized action. If snapshots, designated fact
sources and observed state conflict, report the conflict before making changes.
Do not silently choose stale instructions or manufacture a new authorization.
Create another short handoff only at a real pause/transfer/context-loss boundary,
or when project rules or the user explicitly require one. Update pointers rather
than duplicating state into multiple records.
