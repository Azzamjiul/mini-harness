# Bug Report

## Title
Summary document sometimes says the cleanup completed even when stale notes are still present.

## Context
This workspace simulates a small documentation cleanup task. The failure is not a code crash. The issue is that a previous run left inconsistent notes, and the final explanation did not clearly separate observed facts from assumptions.

## Reproduction
1. Read the current notes and draft explanation in this case.
2. Compare the stated outcome against the actual remaining notes.
3. Notice that the explanation claims the result is already tidy, but the workspace still contains unresolved points and mixed signals.

## Expected
- Investigation output should identify the inconsistency clearly.
- Final explanation should describe the problem in plain technical language.
- Facts, assumptions, and next steps should not be mixed together.

## Actual
- The current material mixes symptoms with conclusions.
- Some notes are still tentative, but the draft explanation sounds final.
- The reasoning is hard to audit quickly.

## Constraints
- Do not modify files outside this case.
- Leave final deliverables in `result/`.
