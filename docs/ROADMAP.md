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
| 10.8 | Rule-aware organization batch review export | `organization_review.py`, `cli.py` | `--export-organization-review`, `--organization-review-output` | review JSON only |
| 10.9 | Apply approved organization review | `organization_apply_review.py`, `cli.py`, `executor.py` | `--apply-organization-review`, `--confirm` | exact confirmation and operation log required |
| 10.10 | Post-apply verification and undo hardening | `organization_verify.py`, existing `executor.py` tests | `--verify-organization-apply` | read-only audit report |
| 10.11 | Resume and edit saved review sessions | `review_session.py`, `cli.py` | `--resume-reviewed-plan` | review-only until exact-confirmed existing apply |
| 10.12 | Review filtering, sorting, and pagination | `review_session.py`, `cli.py` | interactive view commands | display state only |
| 10.13 | Confirmed bulk decisions for current page | `review_session.py`, `cli.py` | `approve-page`, `reject-page`, `undecide-page` | decision-only confirmation |
| 10.14 | Review session quality-of-life polish | `review_session.py`, `cli.py` | existing interactive commands | session-local dirty-state protection |
| 11.0 | Local web architecture contract and threat model | documentation only | none | no runtime behavior |
| 11.1 | Application services and dependency hygiene | `application/`, `reports.py`, narrow CLI entry migration | none | no server or movement changes |
| 11.2 | Secure local web shell and launcher | `web/`, optional web dependencies, bundled assets | separate `organizer.web` launcher | authenticated shell only; no scan or movement |
| 11.3 | Read-only scan dashboard | `web/scan_jobs.py`, scan routes and templates | none | explicit scan/report only; no decisions or movement |
| 11.4 | Read-only review explorer | report-to-review adapter, review routes and templates | none | latest completed scan only; no decision mutation |
| 11.5 | Web review decisions and reviewed-plan saving | generation-bound review holder, decision/save routes and templates | none | explicit save only; no movement |

## Stage 11 Sequence

The local web application is bootAI's intended primary consumer interface. The CLI remains supported for development, scripting, diagnostics, fallback, and safety testing. Static HTML remains read-only. See [WEB_ARCHITECTURE](WEB_ARCHITECTURE.md) and [WEB_THREAT_MODEL](WEB_THREAT_MODEL.md).

### Stage 11.0 — Architecture Contract and Threat Model

Completed as documentation only:

- accepted local web stack and asset policy;
- layer and module ownership;
- root, server, persistence, and accessibility contracts;
- concrete threat model and security controls;
- complete Stage 11 roadmap.

No production code, dependencies, schemas, CLI flags, routes, templates, assets, server, or packaging changed.

### Stage 11.1 — Application Services and Dependency Hygiene

Completed:

- introduced UI-independent scan, immutable review-session, and scan-report/reviewed-plan artifact services while preserving owner modules;
- migrated only report construction and review-session creation/resume CLI entry paths;
- removed mandatory cloud dependencies and archived the historical OpenRouter assistant outside the packaged source tree;
- retained an empty core dependency set and deferred optional web dependencies to Stage 11.2;
- added no server, web package, future artifact parser, preflight/execution service, CLI flag, or movement change.

### Stage 11.2 — Secure Local Web Shell and Launcher

Completed:

- added an isolated FastAPI app factory, direct IPv4-loopback socket binding, dynamic or validated fixed port, one Uvicorn worker, and bounded automatic browser opening;
- added atomic single-use launch authentication, a signed browser-lifetime session, CSRF and exact-Origin helpers, Trusted Host enforcement, locked security headers, generic errors, and no CORS;
- bundled verified HTMX 2.0.10 and Bootstrap 5.3.8 assets with notices and provided a WCAG-oriented welcome screen;
- added only health, launch, authenticated home, and local-static GET routes;
- added no scan, artifact, review, mutation, movement, restore, database, schema, or existing CLI-interface change.

### Stage 11.3 — Read-Only Scan Dashboard

Completed: explicit user-triggered scan, one generation-safe in-process scan job, progress polling, failure handling, report generation, and summary cards. No decisions or movement.

### Stage 11.4 — Read-Only Review Explorer

Completed: browse, filter, sort, and paginate the latest completed scan’s review rows; inspect stable-ID metadata details and approved conflicts; display warnings without rescanning or writing artifacts. No decision mutation.

### Stage 11.5 — Review Decisions and Reviewed-Plan Saving

Completed: Organize (`approved`), Keep here (`rejected`), and Review later (`undecided`) single-row decisions; exact-confirmed current-page decisions; textual dirty state; explicit collision-safe save of every row; and dirty-session scan blocking. There is no autosave, apply, restore, resume, revision, multi-tab merge, or movement.

This is the first completed product-evaluation checkpoint. A user can launch the development web interface, scan a folder, understand findings, inspect suggestions, make review decisions, and save a valid reviewed plan. Apply and undo remain CLI-only while the workflow is evaluated with target users.

### Stage 11.6 — Resume, Stale-State, and Multi-Tab Protection

- Resume reviewed plans.
- Add revision protection, stale-form rejection, multi-tab conflict handling, and source/destination change detection.
- Add no movement.

### Stage 11.7 — Final Plan Preview and Execution Preflight

- Show exact source and destination plans.
- Check missing sources, existing destinations, conflicts, root and symlink safety, and stale metadata.
- Add no movement.

### Stage 11.8 — Confirmed Web Apply and Verification

- Run a fresh preflight and require exact typed confirmation, CSRF, revision protection, and one execution at a time.
- Reuse existing reviewed-plan validation and `executor.py` only.
- Write the operation log and apply result, then run post-apply verification.

### Stage 11.9 — History, Verification, and Confirmed Restore

- Display operation history and verification results.
- Run restore preflight and require exact confirmation.
- Reuse existing executor undo only and write undo-result logs.

### Stage 11.10 — Packaging, Onboarding, Accessibility, and Release Hardening

- Add a low-setup packaged launcher, macOS first and Windows later.
- Hide the terminal for ordinary users, open the browser automatically, provide native folder selection, and support clean shutdown.
- Complete the WCAG 2.2 AA audit, large-folder performance testing, and nontechnical-user testing.

Native desktop development remains an optional final extension after Stage 11. Stage 11 usability should be evaluated at the 11.5 checkpoint rather than postponed until all execution and packaging stages are complete.
