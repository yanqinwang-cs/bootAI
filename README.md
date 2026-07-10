# bootAI

`bootAI` is a cautious local file organizer for scanning folders, reviewing metadata, and applying explicitly approved move plans.

The project is safety-first: dry-run is default, real movement requires exact confirmation, the tool never permanently deletes files by default, the tool never overwrites files, and all real movement goes through approved move plans and operation logs.

## Current Status

Stages 1 through 10.12 are implemented. The tool can currently:

- Scan folders read-only.
- Detect exact duplicates with SHA-256.
- Build duplicate review plans.
- Apply approved duplicate review moves with undo logs.
- Detect review candidates.
- Group document-like files deterministically.
- Load optional read-only organization rules from `AI_Review/config/organization_rules.json`.
- Report alias-normalized anchor decisions for suggested groups, anchors needing a user decision, and ignored terms.
- Infer existing organization patterns for reports without writing rules.
- Export inferred organization rule candidates for manual review.
- Apply accepted organization rule decisions only after exact confirmation.
- Audit how accepted organization rules affect report output.
- Export rule-aware organization suggestions as a JSON batch-review file.
- Apply approved organization-review rows through the existing executor after exact confirmation.
- Verify an organization-review apply result against its operation log and current filesystem state.
- Suggest organization plans.
- Flag isolated code files as candidates for review.
- Optionally refine organization suggestions with local Ollama.
- Apply approved organization plans with undo logs.
- Undo logged move operations.
- Generate read-only JSON reports for manual review or external scheduler runs.
- Generate static HTML report viewers from the same report data.
- Review duplicate, organization, and review-candidate move candidates in a batch CLI session.
- Detect reviewed-plan conflicts before approved batch apply.
- Remember prior batch-review decisions as review state.
- Apply saved reviewed-plan JSON files after validation and exact confirmation.
- Resume saved reviewed-plan sessions, edit decisions, and save a new collision-safe revision.
- Filter, sort, and paginate review-session rows without changing decisions or saved-plan contents.

Stage 10.12 adds display-only review filters, stable sorting, and bounded pagination to new and resumed sessions. View state is not saved and does not change decisions, apply confirmation, movement, operation logs, or undo.

## Setup

Use Python 3 and the standard library. No third-party dependencies are required for the current test suite.

```bash
PYTHONPATH=src python3 -m unittest tests.test_scanner tests.test_safety tests.test_duplicates tests.test_planner tests.test_executor tests.test_review tests.test_grouping tests.test_llm_refinement tests.test_organization_apply tests.test_reports tests.test_review_session tests.test_review_state tests.test_html_report tests.test_scope tests.test_organization_rules tests.test_pattern_inference tests.test_rule_review tests.test_rule_audit tests.test_organization_review tests.test_organization_review_apply tests.test_organization_verify
```

## Quickstart

Run commands with `PYTHONPATH=src` from the repository root:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --duplicates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-organization
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --report
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --html-report
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --review-plans
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --review-plans --ignore-review-state
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --export-rule-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --export-organization-review
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-review AI_Review/reviews/organization_review.approved.json --confirm "APPLY ORGANIZATION REVIEW"
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --verify-organization-apply AI_Review/reviews/organization_review_apply_result.json
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --resume-reviewed-plan AI_Review/review_sessions/reviewed_plan.json
```

Apply commands require exact confirmation:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Undo uses an operation log path printed by an apply command:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --undo-log /path/to/folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

## CLI Examples

Read-only and dry-run commands:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --max-depth 2
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --review-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --project-groups
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-review-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-duplicates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --report
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --report --report-output /path/to/folder/AI_Review/reports/manual_report.json
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --html-report
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --html-report --html-report-output /path/to/folder/AI_Review/reports/manual_report.html
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --review-plans
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --export-rule-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --export-organization-review
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --export-organization-review --organization-review-output AI_Review/reviews/manual_review.json
```

Approved move commands:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-reviewed-plan AI_Review/review_sessions/reviewed_plan.json --confirm APPLY_REVIEWED_PLAN
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-rule-decisions AI_Review/rules/organization_rule_candidates.reviewed.json --confirm "APPLY ORGANIZATION RULES"
```

Local Ollama refinement:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-refined-organization-plan --llm-provider ollama --llm-model qwen2.5:7b --confirm APPLY_REFINED_ORGANIZATION_PLAN
```

## Safety Notes

- Use a small disposable folder for manual testing.
- Inspect dry-run output before using exact confirmation.
- Keep operation logs when testing undo.
- Do not run apply commands on important folders while testing.
- Report mode writes a JSON report file but does not move scanned files.
- HTML report mode writes JSON and HTML report files but does not move scanned files.
- HTML reports do not approve moves, apply moves, perform review actions, write operation logs, or start a server.
- Normal organization suggestions are document-only by default.
- Code/project files are excluded from normal organization suggestions.
- Isolated code files may appear as `orphan_code` candidates for review.
- Protected-context files can appear in factual reports but are excluded from actionable move plans by default.
- Generated web/archive assets and contextual project-output files are excluded from actionable move plans by default.
- Organization suggestions require narrow repeated document-set evidence or an explicit locked anchor.
- Broad anchors such as course codes, project names, personal names, and organization-like terms are non-actionable by default.
- Organization rules are optional and read-only; create `AI_Review/config/organization_rules.json` manually if you need locked anchors, ignored terms, or aliases.
- Locked anchors still require at least two eligible safe files and do not bypass protected/generated/project-output exclusions.
- Reports show anchor decisions after alias normalization: suggested narrow groups, broad anchors needing a decision, and ignored terms.
- Reports show inferred organization patterns as weak preference evidence only.
- Compound folders such as `cs1010x finals/` or `EvoSim images/` can provide report-only evidence.
- Inferred rule candidates are suggestions for manual review; they are not written automatically.
- Rule candidate export writes review JSON only and does not create `organization_rules.json`.
- Rule decisions update `organization_rules.json` only through `--apply-rule-decisions` with exact `APPLY ORGANIZATION RULES` confirmation.
- Accepted organization rules do not move files and do not write operation logs.
- Reports include a rule-aware audit when organization rules exist and explain when rules are missing or invalid.
- Organization-review export writes editable review JSON only. It cannot apply approved rows and does not write operation logs.
- Organization-review apply reads only an explicitly supplied reviewed file, requires exact confirmation, and moves only `approve` rows through `executor.py`.
- Review mode approve/reject/save commands do not move files.
- Review mode stores decision memory under `AI_Review/review_state/review_decisions.json`.
- Review state is decision memory, not an operation log, and does not record filesystem success.
- Review mode applies approved moves only after exact `APPLY_REVIEWED_PLAN` confirmation.
- Review-candidate rows are candidates for review and use `R` IDs in batch review.
- Review mode blocks apply when one source or destination has multiple approved moves.
- Saved reviewed plans are validated as untrusted input before approved moves are applied.
- Resumed reviewed plans keep their explicit decisions authoritative and do not load review-state memory.
- Operation logs remain authoritative for actual successful moves and undo.
- Post-apply verification compares the apply summary, operation log, and filesystem without moving files.
- `executor.py` is the only module that performs real movement.
- Review, grouping, and LLM modules produce facts or suggestions; they do not execute moves.

## Documentation

- [Documentation index](docs/README.md)
- [CLI reference](docs/CLI_REFERENCE.md)
- [Report format](docs/REPORT_FORMAT.md)
- [Sample report](docs/examples/sample_report.json)
- [Manual testing guide](docs/MANUAL_TESTING.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Safety constitution](docs/SAFETY.md)
