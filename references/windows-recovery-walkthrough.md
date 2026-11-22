# Practice resuming a task in two Windows sessions

Create the first file and save a checkpoint in one Codex chat. In a fresh chat, recover the task from disk, verify the saved file and finish the remaining work.

## Before you start

Complete the [Windows first-run checklist](../README.md#windows-first-run-checklist). Open a new, empty local folder as your Codex Desktop project using **This computer**. Use that same folder in both chats. Run each PowerShell block in the order shown, with the project folder as the current directory. You can run the blocks yourself or ask Codex to run them in Windows PowerShell. Within each session, run the setup and the following block in the same PowerShell process so the variables and function are available.

## Setup for both sessions

Use a version of `workctl.py` whose `diagnose` output includes `workspace_available`. If the default path is missing or points to an older copy, edit the `$workctl` line as shown below. Use the same full script path in both sessions and keep PowerShell in the project folder. If the first-run checklist directed you to `py -3`, change `python "$workctl"` to `py -3 "$workctl"` in the function.

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$workctl = Join-Path $HOME '.agents\skills\universal-work\scripts\workctl.py'
# Fallback: replace the line above with the full script path from a current checkout.
# $workctl = 'C:\Projects\universal-work\scripts\workctl.py'
if (-not (Test-Path -LiteralPath $workctl -PathType Leaf)) {
    throw "workctl.py was not found at $workctl. Update the script path in the setup block."
}

$practice = '.universal-work\recovery-practice'
$db = Join-Path $practice 'state.sqlite3'
$first = Join-Path $practice 'first.txt'
$second = Join-Path $practice 'second.txt'

function Invoke-Workctl {
    $output = python "$workctl" --db "$db" @args
    if ($LASTEXITCODE -ne 0) { throw ($output -join [Environment]::NewLine) }
    $output | ConvertFrom-Json
}
```

## Session 1 — Save a checkpoint

```powershell
if (Test-Path -LiteralPath $practice) {
    throw 'Practice files already exist. Use a fresh project folder.'
}
New-Item -ItemType Directory -Path $practice -Force | Out-Null
$specPath = Join-Path $practice 'task.json'
@{
    goal = 'Practice recovering two local files across sessions'
    workspace = (Get-Location).ProviderPath
    criteria = @(
        @{ id = 'first'; type = 'file_nonempty'; path = '.universal-work/recovery-practice/first.txt' }
        @{ id = 'second'; type = 'file_nonempty'; path = '.universal-work/recovery-practice/second.txt' }
    )
    limits = @{ max_steps = 10; max_seconds = 3600 }
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $specPath -Encoding UTF8

$taskId = (Invoke-Workctl new --spec $specPath).task.id
$started = Invoke-Workctl start $taskId
'First practice output' | Set-Content -LiteralPath $first -Encoding UTF8
$hash = (Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash
$note = "Artifact: $first | SHA-256: $hash | Remaining: write second.txt and run finish."
Invoke-Workctl checkpoint $taskId --note $note | Out-Null
$started.task | Select-Object id, deadline
"HANDOFF READY: $taskId"
```

After `HANDOFF READY`, stop the first chat and leave the practice folder in place. The ledger task stays `running`. Start the second chat within one hour of the task's start, in the same project folder.

## Session 2 — Recover and finish

Confirm the first chat stopped. Repeat the setup block, then run this block. It finds the task through the ledger, so you can leave the previous chat closed.

```powershell
$tasks = @((Invoke-Workctl list).tasks)
if ($tasks.Count -ne 1) { throw 'Expected one task in the practice ledger.' }
$taskId = $tasks[0].id
$saved = Invoke-Workctl diagnose $taskId
if (-not $saved.diagnosis.workspace_available) { throw 'Open the original project folder.' }
if ($saved.task.state -eq 'running') {
    Invoke-Workctl block $taskId --reason 'The first practice chat stopped.' | Out-Null
    $saved = Invoke-Workctl diagnose $taskId
}
if ($saved.task.state -ne 'blocked' -or $saved.diagnosis.resume_blockers.Count -gt 0 -or
    $saved.task.claims -ne 0) {
    throw 'Inspect the task diagnosis before continuing.'
}

$checkpoint = $saved.diagnosis.latest_checkpoint
$pattern = '^Artifact: ' + [regex]::Escape($first) + ' \| SHA-256: ([0-9a-f]{64}) \|'
if (-not $checkpoint -or $checkpoint.note -notmatch $pattern) {
    throw 'Keep the task paused. The first file has no saved fingerprint.'
}
$expectedHash = $Matches[1]
if (-not (Test-Path -LiteralPath $first -PathType Leaf)) {
    throw 'Keep the task paused. first.txt is missing.'
}
$actualHash = (Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw 'Keep the task paused. first.txt changed.'
}

Invoke-Workctl resume $taskId | Out-Null
'Second practice output' | Set-Content -LiteralPath $second -Encoding UTF8
$done = Invoke-Workctl finish $taskId
$done.task | Select-Object id, state, deadline
$done.verification.results | Select-Object id, passed, sha256
```

Success means the original task ID reaches `completed` with its original deadline. Both checks show `passed: True`. The `first` result has the SHA-256 saved in the checkpoint, regardless of letter case. The database and both files remain in `.universal-work\recovery-practice` for inspection.

## Try a changed file

Repeat Session 1 in a separate empty project folder. Before Session 2, run this command from that project's root:

```powershell
Add-Content -LiteralPath '.universal-work\recovery-practice\first.txt' -Value 'Deliberate edit'
```

Session 2 should report `Keep the task paused. first.txt changed.` The task stays `blocked` and `second.txt` is still absent. You can confirm the task state and checkpoint with `Invoke-Workctl diagnose $taskId`.
