# Coding procedure

## Inspect the working state

1. Locate the actual project and read applicable repository instructions before editing.
2. Inspect the branch, working tree, existing changes, relevant architecture, and dependency setup.
3. Find the smallest code path that explains the requested behavior.
4. Read nearby tests and project commands to identify the intended contract and validation gates.
5. Record the starting revision and relevant working-tree changes when work spans agents or sessions.
6. Apply the installed language, framework, repository, or deployment skill for domain mechanics.

## Establish the problem

- Translate the request into observable behavior and concrete completion criteria.
- Reproduce reported failures where feasible, capturing the command, input, and actual result.
- Separate the observed symptom from the suspected cause.
- If reproduction is unavailable, document the limit and use the closest meaningful inspection or targeted check.
- Check current primary documentation when behavior depends on uncertain or changing dependencies.
- Do not change dependency versions or project conventions merely for convenience.

## Choose a bounded change

1. Identify the files and interfaces that must change and the behavior they must preserve.
2. Prefer a focused implementation that fits existing project patterns.
3. Use an isolated worktree or checkout when it avoids interference with unrelated work.
4. Preserve user changes; never reset, overwrite, or discard them to simplify the task.
5. If a touched file changes concurrently, reread it and reconcile the new state before editing further.
6. Keep unrelated cleanup separate unless it is required to make the requested behavior correct.

## Implement and integrate

- Use available native development tools and the project's existing build and test paths.
- Inspect the resulting diff for accidental changes, secrets, generated noise, and inconsistent behavior.
- Keep error handling and boundary behavior consistent with the actual interface contract.
- Update directly affected documentation or configuration when the behavior requires it.
- Give parallel workers exclusive file ownership or isolated branches with explicit interface agreements.
- Merge independent worker edits deliberately; inspect conflicts and shared assumptions rather than accepting all patches blindly.
- Recheck callers, schemas, and shared utilities after integration; isolated passes do not prove the combined change works.

## Validate the behavior

1. Run the smallest meaningful check that could fail if the implementation is wrong.
2. For a regression, demonstrate the repaired behavior against the reproducer when possible.
3. Add or update tests when they protect a real contract or recurring failure, not merely mirror implementation details.
4. Skip new tests for reversible, low-impact changes that do not warrant them.
5. Run required project gates and enough integration checks to cover the affected boundaries.
6. Inspect rendered output for visual changes when a runtime or preview is available.
7. Distinguish a passing result from a skipped, unavailable, flaky, or unrelated failing check.
8. Broaden testing only to resolve an identified remaining risk or satisfy a required gate.

## Complete and report

- Verify the final diff and working state after all edits and integrations.
- State the resulting behavior, why it changed, and the meaningful verification performed.
- Report material limitations or remaining failures with their consequence; do not claim tests passed when only code was inspected.
- Perform authorized repository or deployment actions under their own applicable workflow.
- Preserve prepared work if a later action is blocked, and identify the exact blocker.
- Before handoff or compaction, save the revision, changed files, reproducer, completed checks, active worker ownership, and remaining completion criteria.
