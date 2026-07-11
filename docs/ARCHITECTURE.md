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
  -> application coordination
     -> application/scan_service.py
     -> application/review_service.py
     -> application/artifact_service.py
  -> local web shell
     -> web/server.py
     -> web/app.py
     -> web/security.py
     -> web/routes/home.py
  -> batch review
     -> review_session.py
  -> decision memory
     -> review_state.py
  -> approved moves
     -> explicit MovePlanItem values
  -> execution
     -> executor.py
  -> verification
     -> organization_verify.py
  -> undo
     -> operation logs
```

## Module Ownership

| Module | Ownership |
| --- | --- |
| `models.py` | dataclasses shared across stages |
| `safety.py` | shared root-containment validation |
| `scanner.py` | filesystem metadata scanning |
| `duplicates.py` | SHA-256 hashing and exact duplicate grouping |
| `planner.py` | duplicate review planning |
| `review.py` | heuristic review candidate detection and review planning |
| `scope.py` | deterministic organization-scope and orphan-code classification helpers |
| `organization_rules.py` | organization rules loading, validation, and serialization support |
| `grouping.py` | deterministic project grouping and organization suggestions |
| `pattern_inference.py` | report-only inference of existing folder organization patterns |
| `rule_review.py` | organization rule candidate export, reviewed-decision validation, and confirmed config updates |
| `rule_audit.py` | read-only audit of organization-rule effects in reports |
| `organization_review.py` | export and validation of rule-aware organization review JSON; never applies rows |
| `organization_apply_review.py` | approved organization-review conversion, executor orchestration, and apply-result summaries |
| `organization_verify.py` | read-only comparison of apply summaries, operation logs, and filesystem state |
| `llm_refinement.py` | advisory LLM prompt, payload, validation, refined suggestions |
| `ollama_client.py` | local Ollama client only |
| `reports.py` | read-only report assembly, JSON report writing, and authoritative scan-report loading/validation |
| `html_report.py` | read-only static HTML rendering from report dictionaries |
| `review_session.py` | batch review-session construction, decisions, reviewed-plan JSON writing, and saved-plan validation |
| `review_state.py` | persistent human review decision memory |
| `application/scan_service.py` | UI-independent scan/report coordination and summary projection |
| `application/review_service.py` | immutable review-session coordination through existing review owners |
| `application/artifact_service.py` | root-contained listing/loading of scan reports and reviewed plans only |
| `application/view_models.py` | frozen, interface-independent application result types |
| `web/config.py` | frozen per-launch root and ephemeral security configuration |
| `web/server.py` | IPv4-loopback socket binding, browser bootstrap, and single-worker Uvicorn lifecycle |
| `web/app.py` | isolated FastAPI construction, middleware, templates, static mounting, and generic errors |
| `web/security.py` | one-time launch gate, session/CSRF helpers, exact Origin validation, and security headers |
| `web/routes/home.py` | health, single-use launch bootstrap, and authenticated welcome routes only |
| `executor.py` | movement-specific source/destination/symlink validation, approved move execution, operation logs, and undo |
| `cli.py` | substantial current command-line and use-case orchestration |

## Stage 11 Local Web Direction

Stage 11 adds a local web application as bootAI's primary consumer interface. Stage 11.5.2 keeps one generation-bound immutable session while adding strict module projections, per-module saved baselines, and web-owned guided queue state. Fresh web new/stale rows are conservatively normalized to `undecided`; CLI and resumed-plan semantics are unchanged.

The required future dependency direction is:

```text
Local browser
    ↓
Web interface layer
    ↓
Application-service layer
    ↓
Existing deterministic bootAI modules
    ↓
executor.py for explicitly approved movement and undo only
```

The web layer must not reproduce scanner, duplicate, grouping, review, safety, movement, or undo logic. Route modules must never import `executor.py`; only the future execution application service may delegate validated and explicitly approved plans to existing executor functions. Stage 11.5 routes call the application review service through a locked, generation-bound web holder that atomically replaces immutable sessions. Single-row decisions use stable IDs; current-page previews freeze server-held IDs behind one-use opaque tokens; explicit save delegates to the existing saver and includes every row. Query state remains a projection. No route accepts source, destination, root, or output paths, and no apply or restore workflow exists.

The holder exposes dirty state only when decisions differ from the last saved snapshot. A dirty session rejects a new scan with `409 Conflict`; a successful explicit save clears dirty state and records the root-relative collision-safe path. It never autosaves. Stage 11.6 will add reviewed-plan resume, revisions, and multi-tab stale-state rejection.

Consumer presenters group rows by a safety-validated normalized source key and choose one primary card using duplicate → organization → attention precedence. Secondary rows remain visible inside that card and retain independent stable IDs, decisions, conflicts, and serialization. Consumer actions mutate only the primary row through the application service. Advanced review continues to expose all rows. No consumer presenter owns persistence, grouping, duplicate detection, or movement.

Module saves select every authoritative row for one fixed category and reuse `review_session.py` serialization. `saved_decisions` remains the full per-row baseline; a module save advances only its rows, while full save advances all rows. Temporary handled/deferred queue IDs live only in the locked web holder and are invalidated by a new generation.

Each web-server process is bound to one validated immutable root. Browser requests submit stable session-scoped IDs and allowed actions rather than source or destination paths. Existing JSON artifacts remain authoritative; temporary UI, job, security, and revision state may remain in memory, with no initial database.

The current process binds an already-listening IPv4 socket to `127.0.0.1`, normally on an operating-system-selected port, and hands it to one Uvicorn worker with proxy headers and access logging disabled. A one-time launch token establishes a signed browser-lifetime session and immediately redirects away from the token URL. All frontend resources are installed package data; no runtime asset leaves the process origin.

The complete contract is in [WEB_ARCHITECTURE](WEB_ARCHITECTURE.md), and mandatory localhost security controls are in [WEB_THREAT_MODEL](WEB_THREAT_MODEL.md).

## Facts, Suggestions, Approved Moves, Execution, Undo

Facts come from deterministic Python: paths, sizes, hashes, extensions, and inferred deterministic groups. `scanner.py`, `duplicates.py`, `scope.py`, `review.py`, and `grouping.py` produce facts or suggestions.

Suggestions are represented as `MovePlanItem` objects and printed as dry-run plans. Normal organization suggestions are conservative and document-like by default. `scope.py` excludes protected/project/package/application internals, generated web/archive assets, and contextual project-output files from actionable plans. `organization_rules.py` loads `AI_Review/config/organization_rules.json` for grouping and report decisions. `grouping.py` resolves aliases before final anchor decisions, reports broad course/name/project/organization anchors as preference-dependent by default, and creates concrete organization suggestions only for narrow repeated document sets or locked anchors. Exact duplicate groups remain factual; duplicate review plans are stricter actionable candidates. `llm_refinement.py` produces advisory suggestions only and stores them separately from deterministic `ProjectGroup` data.

Reports serialize facts and suggestions into JSON for manual review or external scheduler runs. `pattern_inference.py` enriches reports with weak evidence from existing user folders, such as course-code foldering or person/student foldering. This evidence can rank `Needs decision` anchors and suggest manual rule candidates, but it does not write `organization_rules.json`, create `MovePlanItem` values directly, or approve broad organization. `reports.py` may write a new report file under the scan root, but it does not execute moves or approve actions. `html_report.py` renders the same report dictionary into a static HTML viewer and may write an HTML report file under the scan root. HTML reports do not approve moves, apply moves, perform review actions, write operation logs, or start a server.

Rule review is a configuration workflow, not a movement workflow. `rule_review.py` exports inferred rule candidates to manually editable JSON, validates reviewed decisions as untrusted input, and writes `organization_rules.json` only after exact `APPLY ORGANIZATION RULES` confirmation through the CLI. It does not create `MovePlanItem` values, import `executor.py`, write operation logs, or move files. Rule apply result files are configuration-update audit records only.

Rule-aware audit is report-only. `rule_audit.py` compares conservative defaults with loaded explicit organization rules in memory, reports per-rule effects and broad-impact warnings, and does not create movement-plan items, write rules, import `executor.py`, or move files.

Organization-review export is also report-derived and read-only. `organization_review.py` consumes serialized organization suggestions, anchor decisions, organization rules, and rule-audit context already assembled by `reports.py`. It writes editable review records, not `MovePlanItem` values or execution-ready plans. Stage 10.8 has no path from an approved review row to filesystem movement.

Organization-review apply is a separate confirmed workflow. `organization_apply_review.py` treats the reviewed JSON as user-approved intent, converts only approved rows to `MovePlanItem` values, checks normalized source/destination conflicts, and delegates all preflight and movement to `executor.py`. Its apply-result JSON is a user-readable summary; the executor operation log remains authoritative for successful moves and undo.

Post-apply verification is separate from execution and undo. `organization_verify.py` treats both JSON artifacts as untrusted input, normalizes their paths under the scan root, compares successful source/destination pairs, and checks current source and destination state. It writes an audit report only and does not import or call executor movement functions.

Batch review sessions collect duplicate, deterministic organization, and review-candidate `MovePlanItem` values for command-line review. Review-candidate rows keep `category = "review_candidate"` separate from `review_category` metadata such as `empty`, `temporary`, or `backup_or_copy`. Approve/reject decisions and reviewed-plan JSON records do not execute moves. Approved rows are checked for source and destination conflicts before apply. Saved reviewed-plan JSON is treated as untrusted input when loaded later; `review_session.py` validates it, rejects approved move conflicts, and converts only approved records back into `MovePlanItem` values. Final apply still uses `executor.py`.

Saved batch review sessions can also be resumed through `review_session.py`. Resume reconstructs existing rows and decisions from validated reviewed-plan JSON without scanning or regenerating candidates. Review state is not applied to resumed rows. Saving writes a collision-safe sibling in the same reviewed-plan format; any later apply still uses the existing validator, exact confirmation, conflict checks, and executor path.

Review view state is an in-memory projection over all session rows. `review_session.py` owns deterministic filters, one stable sort key, and pagination. The CLI displays the resulting page, while decisions, conflict checks, saving, and apply continue to use stable IDs and the complete session row list. View state is never serialized.

Bulk page decisions reuse that projection and the existing single-ID decision helpers. A preview freezes the exact stable IDs displayed on the current page, separates changed and idempotent rows, and requires a decision-specific confirmation before mutating in-memory decisions. It does not save or enter the executor path.

Review-session dirty state is a session-local boolean derived only from actual decision changes. It starts clean for generated and resumed sessions, clears after a successful save, and requires exact `QUIT WITHOUT SAVING` confirmation before unsaved decisions are discarded. It is presentation/session state only: it is not serialized and does not alter review-state memory, conflict detection, apply confirmation, or executor behavior.

Review state is separate from reviewed-plan JSON and operation logs. `review_state.py` stores human review decision memory under `AI_Review/review_state/review_decisions.json`, matches remembered decisions back to current rows by source, destination, category, review category, size, and modified time, and flags stale prior decisions when metadata changes. Review state records intent only. It is not an operation log, does not record filesystem success, and is not used for undo.

Approved moves are explicit `MovePlanItem` values accepted by a user-facing flow. Execution is isolated in `executor.py`, which validates and applies approved duplicate, organization, and review-candidate moves only. Undo is driven by operation logs written by `executor.py`.

Planner, review, grouping, and LLM modules do not execute actions. `executor.py` does not decide what should move; it only validates and applies explicit `MovePlanItem` objects. `cli.py` orchestrates user-facing flow.

Stage 8 organization apply reuses `executor.py` for approved organization moves. It does not create another movement subsystem.
