---
name: debugging-triage
description: Structured bug investigation, reproduction, and root-cause analysis
---

# Debugging Triage

Use this skill when a task looks like a bug report, regression, flaky behavior, test failure, or an ambiguous runtime problem that needs fast narrowing.

## Operating Principles

- Start from the observed failure, not from a theory.
- Separate symptoms, reproduction, and root cause.
- Prefer the smallest proof that distinguishes two competing explanations.
- If the issue is intermittent, collect timestamps, inputs, and environment details before changing code.
- Do not patch around a symptom until the failure mode is understood.

## Triage Flow

1. Restate the failure in one sentence.
2. Identify the affected surface area.
3. Find the first point where reality diverges from expectation.
4. Reproduce with the fewest steps possible.
5. Check whether the problem is input-specific, state-specific, timing-specific, or environment-specific.
6. Isolate the layer:
   - parsing
   - validation
   - business logic
   - persistence
   - integration boundary
   - presentation
7. Confirm the root cause with a direct code path, log line, or test.
8. Fix only the minimal behavior necessary.
9. Add a regression test that would fail for the same reason.

## Reproduction Checklist

- Capture the exact command, payload, or user action.
- Record the expected result and the actual result.
- Reduce the input to the smallest failing case.
- Check whether the failure disappears when:
  - the input is simplified
  - the order changes
  - the state is reset
  - external calls are mocked
  - the clock is frozen
- Verify whether the issue survives on a clean run.

## Diagnostic Questions

- Did the failure start after a recent code change?
- Does the issue happen every time or only sometimes?
- Is the bug in local logic or in a dependency boundary?
- Is the failure caused by stale state, caching, or retry behavior?
- Is there a mismatch between the contract the caller expects and the contract the callee actually implements?
- Are there hidden assumptions about null, empty, default, or omitted values?

## Evidence That Matters

- Stack traces
- Failing assertions
- Request and response samples
- Database rows before and after the failure
- Environment variables
- Relevant logs from the smallest time window possible
- Exact test names and line numbers

## Common Failure Shapes

- Off-by-one ranges
- Wrong default selection
- Silent fallback masking the true error
- Data written in one format and read in another
- Race conditions caused by concurrent writes
- Retry logic that hides the first failure
- Validation that is too strict or too loose
- Cache invalidation that does not happen

## Output Format

When summarizing a debugging investigation, use this order:

1. What failed
2. Why it failed
3. Where the evidence is
4. What was changed
5. What test proves the fix

## Quality Bar

- The explanation should point to a concrete line, function, or state transition.
- A good answer should survive a skeptical follow-up asking, "How do you know?"
- If certainty is incomplete, say exactly what is still unproven.
