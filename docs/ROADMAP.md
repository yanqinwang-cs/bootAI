# Roadmap

## Completed Stages

| Stage | Goal | Key Modules | CLI Flags | Safety Status |
| --- | --- | --- | --- | --- |
| 1 | Read-only scanner and metadata report | `models.py`, `safety.py`, `scanner.py`, `cli.py` | base command, `--max-depth` | read-only |
| 2 | Exact duplicate detection with SHA-256 | `duplicates.py` | `--duplicates` | read-only |
| 3 | Dry-run duplicate review plan | `planner.py` | `--plan-duplicates` | dry-run only |
| 4 | Approved duplicate move execution and undo logs | `executor.py` | `--apply-duplicate-plan`, `--confirm`, `--undo-log` | explicit approval required |
| 5 | Heuristic review candidates and dry-run planning | `review.py` | `--review-candidates`, `--plan-review-candidates` | dry-run only |
| 6 | Deterministic project grouping and organization plans | `grouping.py` | `--project-groups`, `--plan-organization` | dry-run only |
| 7 | Optional Ollama LLM group refinement | `llm_refinement.py`, `ollama_client.py` | `--refine-groups`, `--plan-refined-organization` | advisory and dry-run only |
| 7.5 | Documentation and prompt framework | `docs/` | none | documentation only |
| 8 | Apply approved organization plans | `cli.py`, `executor.py` | `--apply-organization-plan`, `--apply-refined-organization-plan`, `--confirm` | explicit approval required |
| 8.5 | Stabilization, manual testing, and release notes | `docs/` | none | documentation only |

## Future Stages

### Stage 9: Overnight Scheduled Report Mode

Goal: generate unattended reports under a configured policy.

Non-goals: no moving without an explicit configured approval policy, no GUI.

### Stage 10: UI Or Richer Review Interface

Goal: provide a safer review surface for candidates, groups, plans, and logs.

Non-goals: no cloud dependency by default, no bypass of CLI safety rules.
