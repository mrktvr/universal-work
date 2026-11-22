# Universal Work

A Codex skill for substantial tasks that span research, code, documents, data, or authorized service operations. It provides a working procedure plus an optional local SQLite ledger for checkpoints and deterministic artifact checks.

## Capabilities and boundaries

- Route work to available host tools and specialist skills, define acceptance criteria, preserve progress, and review the actual deliverable.
- Save task state across local process restarts. Use the [recovery procedure](references/ledger.md#recover-and-check-the-installation) to inspect and continue interrupted work within its original limits.
- Check nonempty files, literal text, exact JSON values, and decimal CSV totals. Completion reruns checks and records hashes.
- Journal external-action outcomes and advisory resource claims for cooperating workers.
- Diagnose saved recovery state and export recorded verification with the [ledger CLI](references/ledger.md#export-verification-evidence).

The skill does not supply missing tools or permissions, schedule autonomous workers, enforce host-wide spending limits, or guarantee exactly-once service mutations. Claims are bookkeeping, not filesystem locks. Checkpoints require the same persistent filesystem. Artifact checks do not establish factual accuracy, code security, or subjective quality; those require separate review. Ledger notes are unencrypted: keep credentials out of them.

## Install

Requires Git to clone. The optional ledger and bundled examples require **Python 3.10+**, using only the standard library; there are no Python packages to install. The host must support loading a `SKILL.md` skill.

Clone the entire directory, including its scripts and references. These commands refuse an existing installation rather than overwriting it.

**macOS / Linux (shell):**

```sh
skill_dir="$HOME/.agents/skills/universal-work"
if [ -e "$skill_dir" ] || [ -L "$skill_dir" ]; then
  printf '%s\n' "Destination already exists: $skill_dir" >&2
else
  mkdir -p "$HOME/.agents/skills" &&
    git clone https://github.com/mrktvr/universal-work.git "$skill_dir"
fi
```

**Windows (PowerShell):**

```powershell
$skillDir = Join-Path $HOME '.agents\skills\universal-work'
if ($null -ne (Get-Item -LiteralPath $skillDir -Force -ErrorAction SilentlyContinue)) {
    throw "Destination already exists: $skillDir"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillDir) | Out-Null
git clone https://github.com/mrktvr/universal-work.git "$skillDir"
if ($LASTEXITCODE -ne 0) { throw 'Git clone failed' }
```

Follow your host's skill-discovery procedure after cloning. Availability in a particular host should be verified there.

### Windows first-run checklist

1. **Check skill discovery in Codex.** Open a new Codex session in the Windows folder where you want to do the work. In the ChatGPT desktop app, type `@` in the composer and look for `universal-work` in the skill picker. In Codex CLI, use `/skills`. If the skill is missing, confirm that `$HOME\.agents\skills\universal-work\SKILL.md` exists in the environment where Codex is running, then restart Codex and check again. [OpenAI skill discovery guide](https://learn.chatgpt.com/docs/build-skills)
2. **Check Python in PowerShell.** From your project folder, run `python --version`. If that command is unavailable or reports an older version, try `py -3 --version`. Use whichever command reports Python 3.10 or newer.
3. **Check the ledger CLI from your project folder.** Point to the installed copy of `workctl.py` so the command works from a separate project. If you installed the skill elsewhere, use that installation's full script path.

   ```powershell
   $workctl = Join-Path $HOME '.agents\skills\universal-work\scripts\workctl.py'
   python "$workctl" --help
   ```

   If you used the Windows launcher in step 2, run `py -3 "$workctl" --help` instead. The help output starts with `usage: workctl.py` and lists the available commands.

   For real tasks, keep the database in your project folder, for example at `.universal-work\state.sqlite3`. Put `--db` before the subcommand. Once that database exists, run `python "$workctl" --db '.universal-work\state.sqlite3' list` to inspect it (use `py -3` in place of `python` if needed). See the [ledger workflow](references/ledger.md#cli-workflow) to create your first task.

## Use

Invoke the skill with a concrete deliverable and its constraints, for example:

```text
Use universal-work to analyze the supplied CSV and produce a checked summary
in this workspace. Preserve the source, state the calculation rules, verify
totals independently, and save a checkpoint so another session can continue.
```

Russian example: `Используй universal-work: проверь данные, подготовь отчёт и сохрани прогресс для продолжения. Укажи выполненные проверки и оставшиеся ограничения.`

Natural requests select procedures; this skill does not register slash commands. Read [SKILL.md](SKILL.md) for the workflow and [the ledger reference](references/ledger.md) before tracking a real task. Store its database in the project workspace, outside the installed skill.

## Run the local example

From the cloned directory:

```sh
python examples/resume_demo.py
```

Use `python3` if that is your Python 3.10+ command. The example runs the real CLI in separate processes, creates a task, starts it, checkpoints and stops it, then launches a fresh worker to inspect, resume, generate, verify, and finish. It fixes the exact expected JSON document before generating output. All fixtures and the ledger live in a temporary directory that is cleaned up; no network calls are made. A successful run ends with `PASS: resumed task completed with independently specified JSON criteria.`

## Verification

```sh
python scripts/test_workctl.py
python examples/resume_demo.py
```

[CI](.github/workflows/ci.yml) is configured for Ubuntu and Windows with Python 3.10 and 3.14. It runs the acceptance suite and example, and requires Linux symlink checks to execute without skips. Tests may skip platform-specific checks on other hosts; inspect the reported skips. A configured matrix is not evidence that its jobs have passed.

The acceptance suite tests the ledger implementation. [Scenario evaluations](evals/README.md) are separate evidence about skill behavior; neither is a demonstrated general improvement in model performance.

## License

See [LICENSE](LICENSE) for the repository's license terms.
