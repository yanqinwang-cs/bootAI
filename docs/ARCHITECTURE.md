# Architecture

## Pipeline

```text
Filesystem
  -> facts
     -> scanner.py
     -> duplicates.py
  -> suggestions
     -> planner.py
     -> review.py
     -> grouping.py
     -> llm_refinement.py
  -> reports
     -> reports.py
  -> batch review
     -> review_session.py
  -> approved moves
     -> explicit MovePlanItem values
  -> execution
     -> executor.py
  -> undo
     -> operation logs
```

## Module Ownership

| Module | Ownership |
| --- | --- |
| `models.py` | dataclasses shared across stages |
| `safety.py` | path validation |
| `scanner.py` | filesystem metadata scanning |
| `duplicates.py` | SHA-256 hashing and exact duplicate grouping |
| `planner.py` | duplicate review planning |
| `review.py` | heuristic review candidate detection and review planning |
| `grouping.py` | deterministic project grouping and organization suggestions |
| `llm_refinement.py` | advisory LLM prompt, payload, validation, refined suggestions |
| `ollama_client.py` | local Ollama client only |
| `reports.py` | read-only report assembly and JSON report writing |
| `review_session.py` | batch review-session construction, decisions, reviewed-plan JSON writing, and saved-plan validation |
| `executor.py` | approved move execution and undo logs |
| `cli.py` | command-line orchestration |

## Facts, Suggestions, Approved Moves, Execution, Undo

Facts come from deterministic Python: paths, sizes, hashes, extensions, and inferred deterministic groups. `scanner.py`, `duplicates.py`, `review.py`, and `grouping.py` produce facts or suggestions.

Suggestions are represented as `MovePlanItem` objects and printed as dry-run plans. `llm_refinement.py` produces advisory suggestions only and stores them separately from deterministic `ProjectGroup` data.

Reports serialize facts and suggestions into JSON for manual review or external scheduler runs. `reports.py` may write a new report file under the scan root, but it does not execute moves or approve actions.

Batch review sessions collect duplicate, deterministic organization, and review-candidate `MovePlanItem` values for command-line review. Review-candidate rows keep `category = "review_candidate"` separate from `review_category` metadata such as `empty`, `temporary`, or `backup_or_copy`. Approve/reject decisions and reviewed-plan JSON records do not execute moves. Approved rows are checked for source and destination conflicts before apply. Saved reviewed-plan JSON is treated as untrusted input when loaded later; `review_session.py` validates it, rejects approved move conflicts, and converts only approved records back into `MovePlanItem` values. Final apply still uses `executor.py`.

Approved moves are explicit `MovePlanItem` values accepted by a user-facing flow. Execution is isolated in `executor.py`, which validates and applies approved duplicate, organization, and review-candidate moves only. Undo is driven by operation logs written by `executor.py`.

Planner, review, grouping, and LLM modules do not execute actions. `executor.py` does not decide what should move; it only validates and applies explicit `MovePlanItem` objects. `cli.py` orchestrates user-facing flow.

Stage 8 organization apply reuses `executor.py` for approved organization moves. It does not create another movement subsystem.
