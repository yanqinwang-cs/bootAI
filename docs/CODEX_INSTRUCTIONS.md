# Codex Instructions

Codex must read this file before implementing future stages.

## Completed Stages

Stages 1 through 7.5 are complete. Current code supports scanning, duplicate detection, dry-run duplicate plans, approved duplicate moves with logs, review candidates, deterministic grouping, local Ollama refinement, and documentation.

## Reuse Before Create

- Before adding a function, check existing modules.
- Before adding a module, check ownership below.
- Do not duplicate safety logic.

## Module Ownership

- `duplicates.py` owns hashing and exact duplicate grouping.
- `review.py` owns heuristic review candidates.
- `grouping.py` owns deterministic project grouping.
- `llm_refinement.py` owns prompt, payload, and validation for LLM group refinement.
- `executor.py` owns moving and undo.

## Do Not Skip Ahead

Implement only the requested stage. Do not implement future roadmap items early.

## Forbidden Behavior

- No permanent file removal.
- No overwriting.
- No automatic moving unless the current stage explicitly says apply.
- No cloud APIs unless the current stage explicitly requests them.
- No new mover modules.
- No hidden side effects in planner, review, grouping, or LLM modules.

## Stage Boundaries

- Stage 8 should reuse `executor.py` for approved organization apply behavior.
- Stage 9 should not move files without an explicit configured approval policy.

## Testing And Git Hygiene

Run the full unittest suite before handoff. Check `git status`. Add only intended files and do not add `test_scan/`.
