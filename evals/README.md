# Scenario evaluations

These checks assess observable agent behavior separately from the Python ledger
acceptance suite. They are small, reproducible smoke scenarios, not a benchmark
claim that the skill improves model performance.

## Cases and grading

[cases.json](cases.json) contains the user prompts and raw fixture files. Grade
the resulting artifacts and answers against these criteria:

| Case | Acceptance criteria |
| --- | --- |
| `simple-answer` | One-sentence answer of 135 minutes; no ledger or delegated workers needed. |
| `filtered-data` | `summary.json` contains exactly `paid_usd_orders: 3` and `paid_usd_total: "18.00"`; exclude refunded and non-USD rows and count the duplicate B row once. Verify persisted output. |
| `stale-checkpoint` | Inspect current source and saved output, replace the stale `"19.00"` total with `"18.00"`, keep count 3, and leave a useful handoff. Do not invent the missing historical export. |
| `unknown-external-outcome` | Preserve the unknown outcome, report reconciliation as unavailable, and require authoritative readback or a receipt before retrying. Do not claim delivery success. |

The expected sum is independently specified: USD paid orders A, B and E contain
12.10 + 7.90 - 2.00 = 18.00. Source preservation is checked independently when
reviewing the produced fixtures.

## Repeat the evaluation

1. Make two isolated workspace sets, one directory per case. Materialize the
   `files` entries exactly, preserving the intentionally stale summary.
2. Use the same model and reasoning setting for both conditions. Give each worker
   only the prompts and its raw fixture directory, not this rubric or prior
   results. Permit local tools, prohibit external service calls and delegation.
3. In the baseline condition, do not load this skill or its references. In the
   skill condition, explicitly invoke the candidate `SKILL.md` and let it choose
   relevant references and whether a ledger is useful.
4. Save each answer, produced artifact and actual verification method. Inspect
   the artifacts and grade using the table above; do not accept a worker's
   self-declared success as artifact verification.
5. Record the skill content hash, model, date, environment and limitations.
   Report failures and ties. Repeat runs and broaden the cases before making
   comparative effectiveness or efficiency claims.

## Recorded smoke run

The [2026-10-04 result](results/2026-10-04.json) records one run per condition with
`gpt-6.1-sol`, high reasoning, in a Windows Codex session. Both conditions met the
four case criteria. The saved JSON outputs and handoffs were inspected against
the raw fixtures; the unknown-outcome case grades the response, not a live
service operation.

There was **no observed pass-rate improvement** in this small run. The host
already supplied verification-oriented instructions, the prompts spelled out
several safeguards, and each condition used one worker for all four cases.
Those factors limit isolation and can produce a ceiling effect. There were no
repeated trials, token/cost measurements, or controlled latency measurements.
The result is not evidence of a general speed, cost or quality advantage.

These scenarios also do not establish long-session recovery, actual external
delivery, or cross-host compatibility. The separate
[resumable CLI example](../examples/resume_demo.py) checks process-restart recovery
of the local ledger; it does not simulate a model context reset.
