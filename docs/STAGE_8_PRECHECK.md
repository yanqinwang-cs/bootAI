# Stage 8 Precheck

This document is the safety gate for Stage 8. Read it before planning or editing.

## Purpose

Apply approved organization plans using the existing executor.

## Non-Goals

- No permanent deletion.
- No overwrite.
- No movement outside scan root.
- No scheduled mode.
- No GUI.
- No cloud APIs.
- No new duplicate detector.
- No new grouping engine.
- No new executor.
- No hidden movement in grouping or LLM modules.

## Required Inspection

Before implementing Stage 8, inspect:

- `src/organizer/models.py`
- `src/organizer/safety.py`
- `src/organizer/grouping.py`
- `src/organizer/llm_refinement.py`
- `src/organizer/executor.py`
- `src/organizer/cli.py`
- `tests/test_grouping.py`
- `tests/test_llm_refinement.py`
- `tests/test_executor.py`

## Implementation Direction

- Organization suggestions should produce explicit `MovePlanItem` values.
- `executor.py` should apply approved `MovePlanItem` values.
- `cli.py` should orchestrate confirmation and display.
- `grouping.py` should not execute moves.
- `llm_refinement.py` should not execute moves.
- `executor.py` should not decide what should move.

Stage 8 must reuse `executor.py`. It must not create a second mover and must not bypass `MovePlanItem`.

## Safety Invariants

- Never permanently delete files.
- Never overwrite files.
- Never move files outside the scan root.
- Validate sources and destinations against the scan root.
- Keep dry-run organization planning non-mutating.
- Require exact explicit confirmation before applying organization plans.
- Write an operation log for every successful move.
- Preserve undo support for real movement.
- Reject direct symlink sources for movement.
- Reject unsafe destination parents, including existing symlink parents that resolve outside the root.
- Do not reorganize files already under `AI_Review` unless a future stage explicitly changes that rule.

## Required Tests

Stage 8 tests should cover at least:

- Dry-run organization plan remains non-mutating.
- Apply organization plan requires exact confirmation.
- Approved organization moves use `executor.py`.
- Operation log is written.
- Undo restores moved organization files.
- Overwrite is rejected.
- Outside-root destination is rejected.
- Symlink source is rejected.
- Unsafe symlink destination parent is rejected.
- Destination collisions do not overwrite.
- `AI_Review` paths are not reorganized accidentally.

## Manual Checklist

- Create a small messy folder.
- Run the dry-run organization plan.
- Confirm no files moved.
- Run apply without exact confirmation.
- Confirm refusal.
- Run apply with exact confirmation.
- Confirm files moved into `Organized/`.
- Confirm operation log exists.
- Run undo.
- Confirm files restored.
- Confirm no overwrite occurred.
- Confirm `test_scan/` was not committed.

## Forbidden Shortcuts

- Do not add another movement module.
- Do not move files from `grouping.py` or `llm_refinement.py`.
- Do not make organization apply implicit.
- Do not skip exact confirmation.
- Do not write logs outside the root.
- Do not repair unsafe paths by silently changing destinations.
- Do not add scheduled mode, GUI, cloud APIs, or a prompt evaluation harness during Stage 8.
