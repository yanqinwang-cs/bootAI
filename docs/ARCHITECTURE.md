# Architecture

## Pipeline

```text
Filesystem
  -> scanner.py
  -> duplicates.py
  -> review.py
  -> grouping.py
  -> llm_refinement.py
  -> planner.py / grouping plan builders
  -> executor.py
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

## Facts, Suggestions, Execution

Facts come from deterministic Python: paths, sizes, hashes, extensions, and inferred deterministic groups. Suggestions are represented as `MovePlanItem` objects and printed as dry-run plans. Execution is isolated in `executor.py`.

Planner, review, grouping, and LLM modules do not execute actions. `executor.py` does not decide what should move; it only validates and applies explicit `MovePlanItem` objects.
