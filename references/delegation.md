# Delegation procedure

## Decide whether parallel work helps

1. Delegate when independent work can reduce delay, improve coverage, or provide useful verification.
2. Keep small, tightly coupled tasks local when coordination would cost more than it saves.
3. Identify the task's critical path before assigning parallel work.
4. Respect the environment's available workers, tool access, budget, and user constraints.
5. Limit concurrency to the workers that have useful independent work now.
6. Do not create a standing swarm, recursive delegation loop, or extra workers merely because capacity exists.

## Partition ownership

- Assign distinct outputs, files, ranges, sources, or questions with explicit boundaries.
- Prefer exclusive ownership of mutable artifacts; use isolated worktrees when shared code would conflict.
- Define interfaces before splitting work that must later combine.
- Keep dependent steps with one owner or schedule them after their prerequisites.
- Give a reviewer the artifact and evaluation criteria rather than the author's desired conclusion.
- Use independent analysis where disagreement could reveal a material error; do not duplicate every task.

## Issue a complete assignment

Provide only the context required to do the work:

- The requested task and how its result contributes to the user's outcome.
- Exact input artifacts, source versions, assumptions, and constraints.
- Ownership boundaries and prohibited edits or external effects.
- The expected output format and concrete completion criteria.
- The evidence to return: methods, source locators, commands or checks, and observed outcomes.
- Time or effort limits when relevant, plus the condition for reporting a blocker.

## Coordinate active work

1. Track each worker's assignment, ownership, status, and dependency on other results.
2. Continue useful main-thread work while independent tasks run.
3. Share changed requirements or source versions promptly with affected workers.
4. Resolve overlapping edits before they create divergent assumptions or overwrite changes.
5. Stop or redirect work that has become redundant or cannot affect the outcome.
6. Treat a worker's request for broader scope as a proposal, not as authorization.
7. Avoid frequent status polling; wait proportionally to the task while keeping the user informed.

## Evaluate returned evidence

- Require each result to identify the assigned task, input or revision version, method, outcome, and limitations.
- Distinguish a proposed answer from executed work and verified evidence.
- Inspect the underlying artifact or source for consequential claims; confidence alone is not evidence.
- Check that verification applies to the returned version rather than an earlier draft.
- Resolve disagreement using source quality, reproducibility, and task fit; majority agreement does not establish truth.
- Reassign only the unresolved part when a result is incomplete or incompatible.

## Integrate and finish

1. Combine outputs against the original user goal and agreed interfaces.
2. Inspect integrated changes for conflicts, gaps, duplicated work, and incompatible assumptions.
3. Run the meaningful final checks across combined boundaries.
4. Confirm every completion criterion has an owner and sufficient evidence.
5. Keep the main agent accountable for the final answer and external actions.
6. Stop completed workers and finish when the requested outcome is adequately verified.
7. Before handoff or compaction, record assignments, source versions, accepted results, pending outputs, ownership, and remaining completion criteria.
