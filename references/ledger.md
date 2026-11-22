# Local task ledger

Use `scripts/workctl.py` for substantial local artifact work that benefits from checkpoints. Resolve its path relative to the installed skill. Use the available Python 3.10+ interpreter (`python3` or `python`); no package installation or API key is required.

## Scope and storage

- Place the database in the task/project workspace, for example `.universal-work/state.sqlite3`, on a local writable filesystem. Do not place it in the installed skill or a network share. SQLite transactions coordinate cooperating processes using this database.
- This is a local task ledger, not an autonomous agent runtime or security boundary. Native tools and other processes can bypass it. Claims are advisory ownership records, not filesystem locks. External actions are journaled but are executed separately by supported host tools.
- Preserve the database with project state if it must survive workspace deletion. Local restart recovery alone is not cloud persistence. For an operational database, close all writers or use SQLite's backup API before copying it; do not copy only the main file while WAL writes are active.
- Record goals, paths, compact progress and external object identifiers. Keep credentials, access tokens and unnecessary sensitive content out of notes/evidence. The ledger is not encrypted and its notes are not automatically redacted.

## Create an explicit contract

Write a UTF-8 JSON spec with the actual absolute workspace path. All criterion paths are relative to that workspace; absolute paths, traversal and resolved escapes are rejected. Use only the fields documented below; unknown fields are errors.

```json
{
  "goal": "Produce a checked result and concise explanation",
  "workspace": "/absolute/path/to/task-workspace",
  "criteria": [
    {"id": "report", "type": "file_nonempty", "path": "report.md"},
    {"id": "heading", "type": "text_contains", "path": "report.md", "needle": "Result"},
    {"id": "count", "type": "json_equals", "path": "result.json", "pointer": "/count", "expected": 3}
  ],
  "limits": {"max_steps": 30, "max_seconds": 1800}
}
```

Use the real Windows absolute workspace path on Windows, correctly escaped in JSON. Determine expected values independently of the deliverable being checked. Never invent an expected value to match generated output. Keep qualitative acceptance criteria in the task plan and verify them separately.

Supported checks:

| Type | Additional fields | Meaning |
|---|---|---|
| `file_nonempty` | none | The relative path resolves to a nonempty regular file |
| `text_contains` | `needle`: nonempty string | UTF-8 text contains the specified literal substring |
| `json_equals` | `pointer`: RFC 6901 string; `expected`: JSON value | The value at the JSON Pointer equals the expectation; empty pointer addresses the document root |
| `csv_sum` | `column`: string; `expected`: decimal string; optional `tolerance`: nonnegative decimal string | Sum the specified column using decimal arithmetic; default tolerance is zero |

`csv_sum` checks all data rows, not a filtered query. Filter data explicitly into the intended output first and independently verify that filtering. JSON numbers use the standard parser's floating-point semantics; represent exact fractional quantities such as money as strings and check those strings, or use `csv_sum` for exact decimal totals. Generic presence, substring and total checks do not establish semantic quality. Files larger than 64 MiB are outside the bundled verifier's scope; use specialist checks and a suitable bounded evidence artifact. CSV text fields can exceed Python's default 131,072-character field limit; the complete file must still fit within 64 MiB.

## CLI workflow

Every command requires `--db PATH` before the subcommand. `new` creates missing database parent directories; other commands reject a nonexistent database. Command output is JSON; errors return exit code 2. Check `ok` and the exit status. Task IDs come from the returned task object; never invent them. A spec is limited to 1 MiB and 128 criteria. `list` shows the latest 100 tasks; `show` includes at most 50 recent actions, 50 claims and 20 events. The complete history remains in SQLite; a limited view is not evidence that older records do not exist.

```text
python <skill>/scripts/workctl.py --db <project>/.universal-work/state.sqlite3 new --spec <project>/task.json
python <skill>/scripts/workctl.py --db <project>/.universal-work/state.sqlite3 start TASK_ID
python <skill>/scripts/workctl.py --db <project>/.universal-work/state.sqlite3 checkpoint TASK_ID --note "Done: ...; evidence: ...; remaining: ...; next: ..."
python <skill>/scripts/workctl.py --db <project>/.universal-work/state.sqlite3 verify TASK_ID
python <skill>/scripts/workctl.py --db <project>/.universal-work/state.sqlite3 finish TASK_ID
```

Pass arguments as structured subprocess arguments where available; otherwise quote paths and data safely for the actual shell. Use JSON files for substantial structured input. Do not paste untrusted text into an executable command string.

Use `list` and `show TASK_ID` to inspect saved state. Use `block TASK_ID --reason TEXT` when a requirement is unavailable, or `stop TASK_ID --reason TEXT` on cancellation/intentional stop. `resume TASK_ID` resumes a blocked/stopped task if unresolved actions and the original limits permit it. `start` begins a new ready task; it does not recreate previous work.

The deadline starts at the first `start` and is not reset by resume. Steps count checkpoints and newly prepared external actions. Limits prevent new ledger work when exhausted; outcome reconciliation, release, inspection and bounded final verification remain available. These limits do not count or intercept arbitrary host tool calls, LLM turns, tokens or spending. Use native limits too when available.

`finish` reruns checks against the current files and stores their hashes. It rejects unresolved actions and outstanding ownership claims. Complete semantic review against these current versions before invoking it. Completed records are terminal snapshots; subsequent artifact changes require a new task and verification. A saved hash identifies the checked bytes; it does not make the file immutable.

## Journal external actions

Use external operations only within the user's authorization. Preparing an entry is not authorization. Choose a stable task-local key for the same logical operation:

```text
... action-prepare TASK_ID --key operation-key --description "Create the authorized test object"
... action-outcome TASK_ID --key operation-key --outcome succeeded --evidence "Service object ID ...; verified by readback ..."
```

Execute the actual service call only after successful preparation. Repeated preparation with the same task/key is rejected, even after success or failure. This is a bookkeeping guard, not service-side deduplication, and it does not prevent a caller from using a different key or another task.

If the response is lost or the worker crashes, treat a prepared entry as unresolved. Inspect actual service state before doing anything else. Record `unknown` when uncertain; record `succeeded` or `failed` only when evidence establishes that outcome. Both prepared and unknown entries block completion. Use the service's idempotency facility where supported; this script supplies no universal exactly-once guarantee. Never use a new key merely to bypass an unresolved operation.

A confirmed failed historical action need not prevent completion after a legitimate alternative resolves the task criteria. Keep the history and explain the repair; do not erase the failed attempt.

## Coordinate cooperating writers

```text
... claim TASK_ID --resource report.md --owner worker-a
... release TASK_ID --resource report.md --owner worker-a
```

Claims conflict across tasks sharing the same database and resolved resource path. On Windows, claim and release comparisons ignore filename case, including for absent outputs and records created by older versions. This is conservative in Windows directories configured to distinguish case. Other platforms retain case-sensitive comparison. Use one owner per resource. Claims survive a worker crash; read the task state and inspect any changes before deliberately releasing the old owner's claim. A claim in a different database offers no coordination. Use isolated worktrees or the service's version checks where needed. A folder claim must not be assumed to lock every descendant.

## Recover and check the installation

Use the original workspace, database and task ID. Run `diagnose TASK_ID` and compare the latest saved checkpoint with the current files, action journal and claims. Use `show TASK_ID` to read the full configured criteria and recent event details.

1. If the task still says `running`, confirm through the host or operator that the previous worker has stopped. The ledger status and checkpoint age alone cannot establish that. Once confirmed, run `block TASK_ID --reason "Previous worker confirmed stopped"` to record the interruption and pause ledger work. If you cannot confirm the worker stopped, leave the task for the operator to resolve.
2. For a blocked or stopped task, reconcile any prepared or unknown action with authoritative readback or a receipt before continuing. If the outcome stays uncertain, leave the task paused and preserve the journal entry. Inspect any artifacts left by the previous worker and resolve its advisory claims before writing the affected resources.
3. Run `resume TASK_ID` once the unresolved actions are settled. It preserves the task ID, original deadline and used steps. If the limits are exhausted, report the result and keep the original records. Change the task scope explicitly only if the user authorizes further work.

`diagnose` reads the committed ledger state. It can find the latest checkpoint even if it has fallen out of the recent event window. It reports ledger-side resume blockers, the latest recorded verification and up to 50 entries each for unresolved actions and outstanding claims. Use the counts and truncation flags to account for additional entries. For a running task, the diagnosis calls for operator confirmation before takeover. Check worker status, current files and external outcomes separately. Keep the diagnosis local because it contains workspace paths, checkpoint notes and action evidence.

## Export verification evidence

Run `export-evidence TASK_ID` and save the JSON output as UTF-8. It records the task state, original limits, action and claim counts, and the last persisted verification. Each result identifies the criterion by its 1-based position in the task spec and includes the check type, outcome, and available SHA-256 and byte count. A task with no verification has `recorded_verification: null`. The export has `format_version: 1`.

The default export omits paths, criterion IDs and expected values, checkpoint notes, action details and artifact contents. Review the remaining metadata and hashes before sharing. The recorded results identify bytes checked at the reported time. Re-run verification before relying on files that may have changed. Both snapshot commands read the existing ledger without changing task state, consuming steps or rechecking artifacts.

To let a reviewer repeat one recorded `json_equals` check, explicitly select it and name the file you intend to share:

```text
... export-evidence TASK_ID --review-criterion report --artifact-name qa-report.json
```

This adds `reviewer_check` with the result's criterion number, your filename label, the JSON Pointer and the expected value. Share the corresponding file alongside the export. Review the expected value for sensitive data before sharing. The label identifies the file in the handoff. Compare the delivered file's SHA-256 and byte count with the numbered result before rerunning the check.

`workctl-json-equals-v1` decodes UTF-8 with an optional BOM, rejects duplicate keys and nonfinite numbers, and resolves the JSON Pointer, with the empty pointer selecting the whole document. Comparison is recursive with exact object keys and ordered arrays. Booleans and numbers are distinct. JSON fractions use Python's finite float parsing and parsed numbers compare by decimal value. Encode exact decimal quantities as strings when needed.

The export carries a recorded outcome and a reproducible check. Authenticating the export or validating claims about a separate input, such as the release ZIP named in a QA report, requires independent evidence of that input or provenance.

## Check the installation

For an installation or a code change, run the bundled deterministic acceptance suite:

```text
python <skill>/scripts/test_workctl.py
```

Tests use temporary fixtures. They verify the ledger's behavior and do not measure whether the skill makes the language model better. Do not rerun the suite for every user task.
