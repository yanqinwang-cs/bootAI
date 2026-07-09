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
     -> scope.py
     -> grouping.py
     -> llm_refinement.py
  -> reports
     -> pattern_inference.py
     -> reports.py
     -> html_report.py
  -> batch review
     -> review_session.py
  -> decision memory
     -> review_state.py
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
| `scope.py` | deterministic organization-scope and orphan-code classification helpers |
| `organization_rules.py` | organization rules loading, validation, and serialization support |
| `grouping.py` | deterministic project grouping and organization suggestions |
| `pattern_inference.py` | report-only inference of existing folder organization patterns |
| `rule_review.py` | organization rule candidate export, reviewed-decision validation, and confirmed config updates |
| `llm_refinement.py` | advisory LLM prompt, payload, validation, refined suggestions |
| `ollama_client.py` | local Ollama client only |
| `reports.py` | read-only report assembly and JSON report writing |
| `html_report.py` | read-only static HTML rendering from report dictionaries |
| `review_session.py` | batch review-session construction, decisions, reviewed-plan JSON writing, and saved-plan validation |
| `review_state.py` | persistent human review decision memory |
| `executor.py` | approved move execution and undo logs |
| `cli.py` | command-line orchestration |

## Facts, Suggestions, Approved Moves, Execution, Undo

Facts come from deterministic Python: paths, sizes, hashes, extensions, and inferred deterministic groups. `scanner.py`, `duplicates.py`, `scope.py`, `review.py`, and `grouping.py` produce facts or suggestions.

Suggestions are represented as `MovePlanItem` objects and printed as dry-run plans. Normal organization suggestions are conservative and document-like by default. `scope.py` excludes protected/project/package/application internals, generated web/archive assets, and contextual project-output files from actionable plans. `organization_rules.py` loads `AI_Review/config/organization_rules.json` for grouping and report decisions. `grouping.py` resolves aliases before final anchor decisions, reports broad course/name/project/organization anchors as preference-dependent by default, and creates concrete organization suggestions only for narrow repeated document sets or locked anchors. Exact duplicate groups remain factual; duplicate review plans are stricter actionable candidates. `llm_refinement.py` produces advisory suggestions only and stores them separately from deterministic `ProjectGroup` data.

Reports serialize facts and suggestions into JSON for manual review or external scheduler runs. `pattern_inference.py` enriches reports with weak evidence from existing user folders, such as course-code foldering or person/student foldering. This evidence can rank `Needs decision` anchors and suggest manual rule candidates, but it does not write `organization_rules.json`, create `MovePlanItem` values directly, or approve broad organization. `reports.py` may write a new report file under the scan root, but it does not execute moves or approve actions. `html_report.py` renders the same report dictionary into a static HTML viewer and may write an HTML report file under the scan root. HTML reports do not approve moves, apply moves, perform review actions, write operation logs, or start a server.

Rule review is a configuration workflow, not a movement workflow. `rule_review.py` exports inferred rule candidates to manually editable JSON, validates reviewed decisions as untrusted input, and writes `organization_rules.json` only after exact `APPLY ORGANIZATION RULES` confirmation through the CLI. It does not create `MovePlanItem` values, import `executor.py`, write operation logs, or move files. Rule apply result files are configuration-update audit records only.

Batch review sessions collect duplicate, deterministic organization, and review-candidate `MovePlanItem` values for command-line review. Review-candidate rows keep `category = "review_candidate"` separate from `review_category` metadata such as `empty`, `temporary`, or `backup_or_copy`. Approve/reject decisions and reviewed-plan JSON records do not execute moves. Approved rows are checked for source and destination conflicts before apply. Saved reviewed-plan JSON is treated as untrusted input when loaded later; `review_session.py` validates it, rejects approved move conflicts, and converts only approved records back into `MovePlanItem` values. Final apply still uses `executor.py`.

Review state is separate from reviewed-plan JSON and operation logs. `review_state.py` stores human review decision memory under `AI_Review/review_state/review_decisions.json`, matches remembered decisions back to current rows by source, destination, category, review category, size, and modified time, and flags stale prior decisions when metadata changes. Review state records intent only. It is not an operation log, does not record filesystem success, and is not used for undo.

Approved moves are explicit `MovePlanItem` values accepted by a user-facing flow. Execution is isolated in `executor.py`, which validates and applies approved duplicate, organization, and review-candidate moves only. Undo is driven by operation logs written by `executor.py`.

Planner, review, grouping, and LLM modules do not execute actions. `executor.py` does not decide what should move; it only validates and applies explicit `MovePlanItem` objects. `cli.py` orchestrates user-facing flow.

Stage 8 organization apply reuses `executor.py` for approved organization moves. It does not create another movement subsystem.
