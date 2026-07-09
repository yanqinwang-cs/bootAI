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
| 9 | Read-only scheduled-compatible report mode | `reports.py`, `cli.py` | `--report`, `--report-output` | report file only |
| 9.5 | Report format stabilization and examples | `docs/`, `tests/test_reports.py` | none | documentation/sample/schema only |
| 10.0 | Batch CLI review and confirmed bulk apply | `review_session.py`, `cli.py` | `--review-plans` | final exact confirmation required |
| 10.1 | Apply saved reviewed plans | `review_session.py`, `cli.py` | `--apply-reviewed-plan`, `--confirm` | validates untrusted saved plan |
| 10.2 | Review-candidate rows in batch review | `review_session.py`, `cli.py` | `--review-plans` | final exact confirmation required |
| 10.2.1 | Reviewed-plan conflict detection | `review_session.py`, `cli.py` | `conflicts` inside `--review-plans` | conflicts block apply |
| 10.3 | Persistent review state and organization memory | `review_state.py`, `review_session.py`, `cli.py` | `--ignore-review-state` | decision memory only |
| 10.4 | Automatic HTML report viewer | `html_report.py`, `reports.py`, `cli.py` | `--html-report`, `--html-report-output` | report files only |
| 10.4.1 | Conservative organization scope and orphan code review | `scope.py`, `grouping.py`, `review.py` | none | scope control only |
| 10.4.2 | Protected context exclusion across actionable plans | `scope.py`, `planner.py`, `review.py` | none | actionable-plan filtering |
| 10.4.3 | Strong anchor organization and generated asset suppression | `scope.py`, `grouping.py`, `review.py` | none | stronger actionable-plan filtering |
| 10.4.4 | Read-only organization rules and anchor decisions | `organization_rules.py`, `grouping.py`, `reports.py` | none | rules are read-only |
| 10.5 | Existing organization pattern inference | `pattern_inference.py`, `reports.py`, `html_report.py` | none | report-only preference evidence |
| 10.6 | Organization rule review workflow | `rule_review.py`, `organization_rules.py`, `cli.py` | `--export-rule-candidates`, `--apply-rule-decisions` | exact confirmation required for config updates |
| 10.7 | Rule-aware organization audit | `rule_audit.py`, `reports.py`, `html_report.py` | none | read-only report audit |

## Future Stages

### Stage 10.8: Static HTML Review Export

Goal: explore static export of reviewed-plan context for review workflows.

Non-goals: no HTML approval or apply behavior without a separately reviewed safety stage.

### Stage 10.9: Filtering, Sorting, Or Pagination

Goal: make large batch review sessions easier to inspect.

Non-goals: no bypass of exact confirmation or executor movement rules.

### Stage 10.10: Resume Or Edit Saved Review Sessions

Goal: load a saved reviewed-plan JSON file for continued review.

Non-goals: no bypass of saved-plan validation.

### Stage 10.11: UI Or Richer Review Interface

Goal: provide a safer review surface for candidates, groups, plans, and logs.

Non-goals: no cloud dependency by default, no bypass of CLI safety rules.
