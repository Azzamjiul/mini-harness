# Rewritten Explanation — Documentation Cleanup Inconsistency

## Observed Facts

1. **The workspace contains stale notes.** The file `sandbox/draft_explanation.md` uses tentative phrases such as "probably" and "maybe" — indicating unresolved items still exist.
2. **The bug report (`sandbox/bug_report.md`) explicitly states** that "the explanation claims the result is already tidy, but the workspace still contains unresolved points."
3. **The workspace notes (`sandbox/workspace_notes.md`) confirm** the draft is "directionally correct but verbose" and flag that "the word 'complete' is used too early."
4. **The draft explanation is written in backward order:** it opens with a conclusion ("the task mostly worked"), then mentions a symptom, then backfills a guess about causality.

## Separating Facts from Assumptions

| Statement | Category | Source |
|---|---|---|
| "The task mostly worked and the notes were cleaned up" | **Assumption** — not backed by current file state | draft_explanation.md |
| "There are still a few things that maybe mean the result is not actually complete" | **Assumption** (hedged language, no specific items listed) | draft_explanation.md |
| "The explanation jumps around" | **Fact** — verifiable by reading the file top to bottom | draft_explanation.md structure |
| "There is no strong separation between observation and inference" | **Fact** — a single read confirms mixed statements | draft_explanation.md content |
| "The current state is confusing for the next person" | **Inference** — reasonable, but not an observed defect in itself | Derived from above facts |

## Root Cause

The inconsistency is not a runtime bug — it is a **documentation-process failure**:

- The writer declared the cleanup complete without cross-checking the actual workspace state.
- Observations and interpretations were written in the same paragraph, making the reasoning non-auditable.
- The narrative ordering (conclusion → evidence → guess) inverted the logical chain that a reviewer needs to follow.

## Resolution

A two-part fix was applied:

1. **Investigation summary** — written following the debugging-triage output format (What failed → Why → Evidence → Change → Test). This isolates facts, assumptions, and root cause into separate sections.
2. **This rewritten explanation** — restructured to present facts first, assumptions second, and conclusions last. Every key statement is labeled with its source and category.

## Verification

- Read the rewritten output from top to bottom.
- Every factual claim can be traced back to a specific file or line in the workspace.
- Every assumption is explicitly tagged.
- No statement claims finality ("complete", "cleaned up") without first showing the supporting evidence.
