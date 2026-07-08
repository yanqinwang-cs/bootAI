# Codex Instructions

Codex must read this file before implementing future stages.

## Before Editing

- Use Plan Mode before editing.
- State the requested stage.
- State explicit non-goals.
- List intended files before editing.
- Inspect existing modules before adding code.
- Reuse existing functions where possible.
- Respect module ownership.
- Do not skip ahead.
- Do not duplicate existing subsystems.
- Do not touch `test_scan/`.

## Completed Stages

Stages 1 through 10.0 are complete. Current code supports scanning, duplicate detection, dry-run duplicate plans, approved duplicate moves with logs, review candidates, deterministic grouping, local Ollama refinement, documentation, approved organization moves through `executor.py`, manual testing guidance, release notes, read-only JSON reports, and batch CLI review of duplicate and organization plans.

## Reuse Before Create

- Before adding a function, check existing modules.
- Before adding a module, check ownership below.
- Do not duplicate safety logic.

## Module Ownership

- `duplicates.py` owns hashing and exact duplicate grouping.
- `review.py` owns heuristic review candidates.
- `grouping.py` owns deterministic project grouping.
- `llm_refinement.py` owns prompt, payload, and validation for LLM group refinement.
- `reports.py` owns read-only report assembly and JSON report writing.
- `review_session.py` owns batch review-session construction, decisions, and reviewed-plan JSON writing.
- `executor.py` owns moving and undo.

## Do Not Skip Ahead

Implement only the requested stage. Do not implement future roadmap items early.

## Stage-Boundary Checklist

Answer these before editing:

- Am I modifying only files allowed by this stage?
- Am I adding behavior from a future stage?
- Am I duplicating an existing module?
- Am I bypassing `executor.py` for movement?
- Am I adding hidden side effects?
- Am I preserving dry-run defaults?
- Am I preserving undo and operation-log requirements?
- Am I touching `test_scan/`?

## Forbidden Behavior

- Never permanently delete files.
- No overwriting.
- No automatic moving unless the current stage explicitly says apply.
- No cloud APIs unless the current stage explicitly requests them.
- No new mover modules.
- No hidden side effects in planner, review, grouping, or LLM modules.

## Stage Boundaries

- Stage 8 reuses `executor.py` for approved organization apply behavior.
- Do not create a second mover for organization changes.
- Do not bypass `MovePlanItem`.
- Stage 9 report mode writes report files only and must not move scanned files.
- Stage 10.0 review mode approve/reject/save commands must not move files.
- Stage 10.1 saved-session resume remains future work.
- Stage 10.2 review-candidate tables remain future work.

## Testing And Git Hygiene

- Run the full unittest suite before handoff.
- Inspect `git status`, `git diff`, and `git diff --staged` before committing.
- Commit only specific intended files.
- Do not use `git add .` casually.
- Do not add `test_scan/`.
