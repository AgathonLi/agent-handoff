# Resume checklist

Work through this before acting on a handoff. Skipping it is how an agent
confidently continues from context that no longer holds.

## 1. Locate and assess

- [ ] `python scripts/list_handoffs.py` — confirm which handoff is most recent
- [ ] `python scripts/check_staleness.py <file>` — get a freshness verdict
- [ ] If `VERY_STALE`: prefer creating a fresh handoff over resuming this one
- [ ] Confirm the reported project root matches the project you intend to work in

## 2. Read completely

- [ ] Read the entire handoff before taking any action
- [ ] If "Continues from" is set, read the predecessor too
- [ ] Note anything marked as an assumption — those need verification, not trust

## 3. Verify the environment

- [ ] Current directory matches the handoff's `Project` field
- [ ] Current git branch matches the handoff's `Branch` field, or you understand
      why it differs
- [ ] Files listed in "Critical Files" still exist
- [ ] `git status` is consistent with what "Files Modified" describes

## 4. Re-check the premises

- [ ] Each item in "Assumptions Made" still holds — verify, do not assume
- [ ] Each item in "Blockers and Open Questions" — resolved, or still blocking?
- [ ] Decisions in "Decisions Made" still apply given any changes since
- [ ] Nothing in "Potential Gotchas" has been silently triggered already

## 5. Check for conflicts

- [ ] Files changed since the handoff do not conflict with the planned next steps
- [ ] No one else rewrote the area you are about to touch
- [ ] Dependencies and tooling still install and run

## 6. Confirm before diverging

- [ ] If the plan in "Immediate Next Steps" no longer makes sense, say so before
      substituting your own plan
- [ ] If the handoff conflicts with observed project state, surface the conflict
      rather than picking a side silently

## 7. Begin

- [ ] Start at "Immediate Next Steps" item 1
- [ ] Keep "Key Patterns Discovered" in view so new code matches the codebase
- [ ] As you work, mark completed items and record new findings
- [ ] Before finishing, create the next handoff with `--continues-from`

## Red flags

Stop and report rather than proceeding when:

- The handoff references files that no longer exist and the plan depends on them
- The branch differs and the handoff's work appears already merged or reverted
- "Important Context" contradicts what the code actually does now
- Staleness is `VERY_STALE` and the next steps assume a state you cannot confirm
