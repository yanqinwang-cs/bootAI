# Codex Instructions

Codex must read this file before implementing future stages.

## Before Editing

- Use Plan Mode before editing.
- State the requested stage.
- State explicit non-goals.
- List intended files before editing.
- Inspect existing modules before adding code.
- Before any Stage 11 implementation, read `WEB_ARCHITECTURE.md` and `WEB_THREAT_MODEL.md` completely.
- Reuse existing functions where possible.
- Respect module ownership.
- Do not skip ahead.
- Do not duplicate existing subsystems.
- Do not touch `test_scan/`.

## Completed Stages

Stages 1 through 10.14 and Stages 11.0 through 11.1 are complete. Current code supports the existing scan, review, report, apply, verification, and undo workflows plus UI-independent scan, review, and narrowly scoped artifact services. Stage 11.1 migrates only CLI report construction and review-session creation/resume, removes mandatory cloud dependencies, and archives the unrelated historical OpenRouter assistant outside the package. It adds no web runtime, movement path, schema, or CLI flag.

## Reuse Before Create

- Before adding a function, check existing modules.
- Before adding a module, check ownership below.
- Do not duplicate safety logic.

## Module Ownership

- `duplicates.py` owns hashing and exact duplicate grouping.
- `review.py` owns heuristic review candidates.
- `scope.py` owns deterministic organization-scope and orphan-code classification helpers only.
- `organization_rules.py` owns organization-rules loading, validation, and serialization support.
- `grouping.py` owns deterministic project grouping.
- `pattern_inference.py` owns report-only inference of existing folder organization patterns.
- `rule_review.py` owns organization rule candidate export, reviewed-decision validation, and confirmed config updates. It must not import `executor.py` or create `MovePlanItem` values.
- `rule_audit.py` owns read-only organization-rule effect audits. It must not import `executor.py`, create movement-plan items, write rules, or move files.
- `organization_review.py` owns rule-aware organization review JSON export and validation. It consumes report dictionaries and must not create `MovePlanItem` values, import `executor.py`, apply rows, or move files.
- `organization_apply_review.py` owns approved organization-review conversion and result summaries. It may call only `executor.apply_move_plan()` for movement and must not rescan or regenerate suggestions.
- `llm_refinement.py` owns prompt, payload, and validation for LLM group refinement.
- `reports.py` owns read-only report assembly and JSON report writing.
- `reports.py` also owns public scan-report loading and validation for its existing format.
- `html_report.py` owns read-only static HTML rendering from report dictionaries.
- `review_session.py` owns batch review-session construction, decisions, reviewed-plan JSON writing, saved-plan validation, and conversion back to `MovePlanItem` values.
- `review_state.py` owns persistent human review decision memory.
- `safety.py` owns shared root-containment validation.
- `application/scan_service.py` coordinates report construction and derives interface summaries without I/O or movement.
- `application/review_service.py` coordinates immutable review sessions through `review_session.py` and `review_state.py`; it never imports the executor.
- `application/artifact_service.py` lists and loads only scan reports and reviewed plans for the first web MVP. Future artifact kinds remain deferred.
- `application/view_models.py` owns frozen interface-independent application results.
- `executor.py` owns movement-specific source/destination/symlink preflight, moving, operation logs, and undo.

## Stage 11 Guardrails

- The local web application is the intended primary consumer interface; do not describe the CLI as the intended ordinary-user interface.
- Do not skip Stage 11 safety gates or combine roadmap stages merely because later functionality is convenient.
- Web routes must not import `executor.py`. Only the future `application/execution_service.py` may delegate to existing executor functions.
- Application services must reuse current scanner, duplicate, grouping, review-session, safety, executor, verification, report, and artifact ownership.
- Do not create separate CLI and web implementations of the same workflow.
- Browser requests must submit stable root-bound IDs and allowed actions, never arbitrary source or destination paths.
- One validated root is immutable for each server process. Changing roots requires a new process.
- Bind to `127.0.0.1`, use one worker, and never default to `0.0.0.0`.
- Treat browser values and loaded JSON artifacts as untrusted.
- Every mutation requires POST, a signed session, session-bound CSRF, same-origin validation, and revision protection. GET remains read-only.
- Use a one-time launch token, Trusted Host validation, restrictive security headers, no CORS, and no arbitrary file-serving endpoint.
- Bundle frontend assets locally. No CDN, remote fonts, analytics, telemetry, external scripts, or runtime cloud APIs.
- Do not add a database initially; existing JSON artifacts remain authoritative.
- Accessibility targets WCAG 2.2 AA from the first web screen.
- Do not add web apply before Stage 11.8 or web restore before Stage 11.9.
- Do not begin native desktop development during Stage 11. A small packaged folder chooser in Stage 11.10 is not a desktop UI architecture.
- Do not claim that moving files on the same filesystem saves or recovers storage.
- Stage 11.0 adds documentation only: no production code, dependencies, schemas, CLI flags, templates, routes, assets, launchers, or packaging.
- Stage 11.1 adds no server, web package, preflight service, execution service, web dependency, new CLI flag, future artifact parser, or movement change.
- Core mandatory dependencies contain no cloud SDK or dotenv package. Cloud/OpenRouter references are permitted only in `legacy/openrouter_code_assistant/`, which is excluded from packaging and runtime.
- `application/__init__.py` contains public exports only; services reuse `safety.py` and owner validators rather than implementing shared path validation.

## Do Not Skip Ahead

Implement only the requested stage. Do not implement future roadmap items early.

## Stage-Boundary Checklist

Answer these before editing:

- Am I modifying only files allowed by this stage?
- Am I adding behavior from a future stage?
- Am I duplicating an existing module?
- Am I bypassing `executor.py` for movement?
- Am I adding hidden side effects?
- Am I preserving dry-run defaults?
- Am I preserving undo and operation-log requirements?
- Am I touching `test_scan/`?

## Forbidden Behavior

- Never permanently delete files.
- No overwriting.
- No automatic moving unless the current stage explicitly says apply.
- No cloud APIs unless the current stage explicitly requests them.
- No new mover modules.
- No hidden side effects in planner, review, grouping, or LLM modules.

## Stage Boundaries

- Stage 8 reuses `executor.py` for approved organization apply behavior.
- Do not create a second mover for organization changes.
- Do not bypass `MovePlanItem`.
- Stage 9 report mode writes report files only and must not move scanned files.
- Stage 10.0 review mode approve/reject/save commands must not move files.
- Stage 10.1 saved reviewed plans must be treated as untrusted input.
- Stage 10.2 review-candidate rows use `category = "review_candidate"` and separate `review_category` metadata.
- Stage 10.2.1 reviewed-plan conflicts must be surfaced and must block apply.
- Stage 10.3 review state records human decisions only; it is not an operation log and must not record filesystem success.
- Stage 10.3 remembered decisions must not bypass exact confirmation.
- Stage 10.4 HTML reports must not include approval buttons, apply buttons, review actions, server behavior, or operation-log behavior.
- Stage 10.4.1 normal organization scope is conservative and document-like by default.
- Stage 10.4.1 orphan code is a candidate for review only and must not be broadly organized.
- Stage 10.4.2 protected-context files must not become actionable move candidates by default.
- Stage 10.4.2 exact duplicate facts must remain distinct from duplicate review candidates.
- Stage 10.4.3 generated web/archive assets and contextual project-output files must not become actionable move candidates by default.
- Stage 10.4.3 organization suggestions must use strong grouping evidence, not confidence alone.
- Stage 10.4.4 organization rules are read-only; aliases resolve before decisions, ignored terms win over locked anchors, locked anchors do not bypass scope exclusions, and broad anchors stay non-actionable by default.
- Stage 10.5 pattern inference is report-only; it must not write rules, create `MovePlanItem` values directly, or change apply behavior.
- Stage 10.6 rule review exports inferred candidates and updates `organization_rules.json` only after exact confirmation. It must not move files.
- Stage 10.7 rule-aware audit is report-only; it must not write rules, create movement-plan items, import `executor.py`, or move files.
- Stage 10.8 organization-review export writes review JSON only; it must not create execution-ready plans, write operation logs, or apply rows.
- Stage 10.9 organization-review apply requires exact confirmation before file access, converts only approved rows, and delegates all movement to `executor.py`.
- Stage 10.10 verifies organization-review apply results against the filesystem and executor operation log, and hardens undo verification with temporary-directory tests. It must add no organization logic or mover, automatic undo, rule changes, LLM behavior, or GUI work.
- Stage 10.11 resumes only existing batch reviewed-plan JSON. Saved decisions are authoritative, review state is not applied, save is collision-safe, and confirmed apply must reuse the existing validator and executor path.
- Stage 10.12 view state filters, sorts, and paginates display rows only. Stable IDs, all session rows, decisions, save ordering, apply confirmation, and executor behavior remain unchanged.
- Stage 10.13 bulk decisions target only exact stable IDs on the current displayed page, require action-specific typed confirmation, remain in memory until save, and must not enter the executor path.
- Stage 10.14 unsaved-decision state is session-local, changes only after actual decision edits, clears only after successful save, and must not alter reviewed-plan schemas, review state, conflicts, apply confirmation, or executor behavior.
- Stage 11.0 freezes architecture, security, accessibility, and roadmap contracts only.
- Stage 11.1 introduces application services and dependency hygiene without a server or movement changes.
- Stage 11.2 adds only the secure local web shell and launcher; no scan workflow.
- Stage 11.3 adds read-only scanning; no decisions or movement.
- Stage 11.4 adds read-only review exploration; no decision mutation.
- Stage 11.5 adds review decisions and saving only; no movement, and it is the first product-evaluation checkpoint.
- Stage 11.6 adds resume, revision, stale-state, and multi-tab protection; no movement.
- Stage 11.7 adds final-plan preview and read-only execution preflight; no movement.
- Stage 11.8 is the first stage permitted to add confirmed web apply, using existing reviewed-plan validation and `executor.py` only.
- Stage 11.9 is the first stage permitted to add confirmed web restore, using existing executor undo only.
- Stage 11.10 owns packaging, onboarding, accessibility audit, performance testing, and release hardening.

## Testing And Git Hygiene

- Run the full unittest suite before handoff.
- Inspect `git status`, `git diff`, and `git diff --staged` before committing.
- Commit only specific intended files.
- Do not use `git add .` casually.
- Do not add `test_scan/`.
