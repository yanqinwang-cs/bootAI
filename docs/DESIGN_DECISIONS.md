# Design Decisions

## Deterministic Python Is Source Of Truth

Filesystem facts, hashes, review candidates, and deterministic groups are computed in Python. LLM output can refine names and subfolders, but it cannot replace those facts.

## SHA-256 For Exact Duplicates

SHA-256 gives deterministic exact-content matching. Duplicate detection reports groups and plans review moves; it does not make disposal claims.

## Dry-Run Planning Before Execution

Planning and execution are separate so users can inspect every suggested action. `MovePlanItem` is the boundary between suggested action and approved execution.

## `executor.py` Is The Only Movement Module

Keeping movement in one module makes validation, logs, and undo behavior auditable. Review, grouping, prompt, and planner modules do not execute actions.

## Operation Logs Are Required

Every applied move records source, destination, success, and message. Undo reads those logs and validates paths again.

## Cautious Review Categories

Heuristics use cautious categories such as temporary, empty, and backup-or-copy. They identify candidates for review, not final decisions.

## Deterministic Grouping Before LLM Use

Course-code and token grouping happen before any model call. The LLM receives compact metadata and returns advisory refinements only.

## Local Ollama Before Cloud APIs

Stage 7 supports only local Ollama. Cloud APIs are intentionally out of scope until a future stage explicitly requests them.

## Strict JSON And Python Validation

The model must return JSON. Python validates every field and rejects invalid output instead of repairing it silently.

## Prompt Documentation And Versions

Prompts are engineering artifacts. They are documented, versioned, and evaluated separately from runtime code.

## Organization Apply Reuses `executor.py`

Stage 8 added approved organization moves without adding another movement subsystem. The CLI flattens reviewed `MovePlanItem` values from organization suggestions and sends them through `executor.py`, preserving root validation, overwrite refusal, operation logs, and undo.

## Stage 8.5 Stabilizes Before Stage 9

Stage 8.5 improves release-readiness with manual testing guidance and release notes. It does not add scheduled mode, GUI behavior, cloud APIs, or new movement behavior.
