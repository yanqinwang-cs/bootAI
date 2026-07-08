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
| `executor.py` | approved move execution and undo logs |
| `cli.py` | command-line orchestration |

## Facts, Suggestions, Approved Moves, Execution, Undo

Facts come from deterministic Python: paths, sizes, hashes, extensions, and inferred deterministic groups. `scanner.py`, `duplicates.py`, `review.py`, and `grouping.py` produce facts or suggestions.

Suggestions are represented as `MovePlanItem` objects and printed as dry-run plans. `llm_refinement.py` produces advisory suggestions only and stores them separately from deterministic `ProjectGroup` data.

Approved moves are explicit `MovePlanItem` values accepted by a user-facing flow. Execution is isolated in `executor.py`, which validates and applies approved moves only. Undo is driven by operation logs written by `executor.py`.

Planner, review, grouping, and LLM modules do not execute actions. `executor.py` does not decide what should move; it only validates and applies explicit `MovePlanItem` objects. `cli.py` orchestrates user-facing flow.

Future Stage 8 must reuse `executor.py` for approved organization moves. It must not create another movement subsystem.
