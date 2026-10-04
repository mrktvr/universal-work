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

On restart, run `show`, inspect current files and outstanding actions/claims, reconcile uncertainty, then resume if allowed. Never replace the database or silently create a fresh task to reset exhausted limits. Change the task scope explicitly if the user authorizes further work.

For an installation or a code change, run the bundled deterministic acceptance suite:

```text
python <skill>/scripts/test_workctl.py
```

Tests use temporary fixtures. They verify the ledger's behavior and do not measure whether the skill makes the language model better. Do not rerun the suite for every user task.
