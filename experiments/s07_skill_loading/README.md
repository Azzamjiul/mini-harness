# s07 Skill Loading Experiments

This experiment uses one self-contained case per skill configuration.

Run flow:
1. Copy the case's `skills/` into the workspace `skills/` directory used by `agents/s07_skill_loading.py`.
2. Run the agent against that case's `prompt.md`.
3. Compare the output in `result/` with `expected.md`.

Cases:
- `case_00_no_skills`
- `case_01_debugging_only`
- `case_02_writing_only`
- `case_03_both_skills`

Each case has the same sandbox input so the only variable is which skills are present.
