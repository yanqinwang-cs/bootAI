# Release Notes

## Stage 11.2 — Secure Local Web Shell and Launcher

Stage 11.2 adds bootAI's first local web runtime. `python3 -m organizer.web --root <folder>` validates and locks one root, binds an already-listening IPv4 socket to `127.0.0.1` on a dynamic or explicitly selected port, and runs one Uvicorn worker with proxy headers and access logging disabled. Automatic launch waits for the minimal unauthenticated health check; `--no-browser` and browser-open failure print the private single-use launch URL.

The FastAPI app disables documentation endpoints and exposes only health, single-use launch bootstrap, authenticated welcome, and package-local static GET routes. The launch token is consumed atomically, creates a minimal signed browser-lifetime session, and redirects to a clean URL. Trusted Host enforcement, CSRF and exact same-origin helpers, a locked CSP and security-header middleware, generic production errors, and no CORS establish the mutation-security foundation without adding a mutation route.

HTMX 2.0.10 and Bootstrap 5.3.8 are bundled from verified official release files with their published SHA-384 values and license notices. The accessible first screen confirms the immutable root, offline/local operation, and that no scan or movement has occurred. Exact optional dependencies are isolated in `web` and `web-test`; core dependencies remain empty.

No existing CLI flag, application service, artifact format, JSON schema, scan/report/review workflow, executor path, movement, verification, undo, or legacy code changes. Stage 11.3 has not begun.

## Stage 11.1 — Application Services and Dependency Hygiene

Stage 11.1 adds UI-independent application services for scan-report construction, immutable review-session workflows, and deterministic listing/loading of scan reports and reviewed plans. These services delegate to existing report, review-session, review-state, safety, scanner, grouping, and Ollama owners; they create no second scanner, review engine, saver, or movement path.

The CLI now uses the scan service for `--report` and `--html-report`, and the review service for `--review-plans` and `--resume-reviewed-plan`. The interactive command loop, confirmations, apply, undo, organization-review, verification, executor calls, output formats, schemas, and flags are unchanged.

Mandatory `openai` and `python-dotenv` dependencies and their lockfile transitive packages are removed. Core packaging is explicitly restricted to `src/`, Python remains `>=3.13`, and Stage 11.1 adds no web dependencies. The unrelated historical OpenRouter assistant is preserved under `legacy/openrouter_code_assistant/` as unsupported, unpackaged legacy code.

No web server, route, template, asset, preflight service, execution service, future artifact parser, or movement behavior is added in Stage 11.1.

## Stage 11.0 — Local Web Architecture Contract and Threat Model

Stage 11.0 defines the documentation contract for bootAI's future primary local web interface. It accepts FastAPI, Jinja2, HTMX, Bootstrap, minimal vanilla JavaScript, and Uvicorn; requires local assets, loopback-only single-worker serving, one immutable validated root, existing JSON persistence, WCAG 2.2 AA, and a UI-independent application-service layer.

The threat model treats the browser and loaded artifacts as untrusted and requires a one-time launch token, signed session, CSRF, Origin and Host validation, POST-only mutations, restrictive security headers, stable IDs instead of paths, revision protection, fresh preflight, and executor-only movement and undo.

This stage changes documentation only. It adds no server, routes, application-service modules, dependencies, templates, static assets, CLI flags, schemas, packaging, or production behavior. The CLI remains the current implemented interface while the local web application is the intended primary consumer interface for later Stage 11 work.

## Current Status Through Stage 10.14

Stage 10.14 polishes the interactive review session with grouped help, specific invalid-command guidance, session-local unsaved-decision tracking, exact `QUIT WITHOUT SAVING` protection, root-relative session/save summaries, and clearer conflict display. Reviewed-plan schemas, review-state semantics, apply confirmation, and movement behavior are unchanged.

Stage 10.13 adds previewed and typed-confirmed decision changes for the current displayed review page. Idempotent rows are reported separately, hidden and off-page rows remain unchanged, decision-filtered views are recalculated safely, and saving remains explicit.

Stage 10.12 adds deterministic filtering, one-key sorting, pagination, and view-state display to both new and resumed review sessions. View commands operate only on an in-memory projection; stable IDs continue to target the complete session, and saved reviewed plans include all rows without persisting view state.

Stage 10.11 adds a single-purpose resume workflow for saved batch reviewed-plan JSON. It validates untrusted files, reconstructs stable rows without rescanning, preserves explicit decisions, supports `undecide`, and saves collision-safe revisions without overwriting the input. Review state does not alter resumed decisions, and existing exact-confirmed apply behavior remains executor-owned.

Stage 10.10 adds a single-purpose read-only verification command for Stage 10.9 apply results. It strictly validates the apply summary and referenced executor operation log, compares normalized successful move pairs, checks current filesystem state, and writes a collision-safe audit report. Undo behavior is unchanged and receives additional temporary-directory regression coverage.

Stage 10.4 adds a static HTML report viewer. `--html-report` writes both the existing JSON report and a browser-openable HTML rendering from the same report data without approving or applying moves.

Stage 10.4.1 makes organization conservative by default. Normal organization suggestions are limited to low-risk document-like files, standalone HTML is included only when it does not look like web-project HTML, and isolated code files may be flagged as `orphan_code` candidates for review instead of normal organization suggestions.

Stage 10.4.2 excludes protected contexts from actionable move plans. Exact duplicate facts can still report byte-for-byte matches, but duplicate review plans, review candidate plans, organization suggestions, batch review rows, and approved saved reviewed-plan items exclude protected contexts by default.

Stage 10.4.3 requires strong organization anchors, suppresses weak top-level token groups, assigns role-based subfolders after grouping, and excludes generated web/archive and contextual project-output assets from actionable plans.

Stage 10.4.4 adds optional read-only organization rules loaded from `AI_Review/config/organization_rules.json` when present. It reports alias-normalized anchor decisions as suggested narrow groups, broad anchors needing a user decision, and ignored terms. Ignored terms win over locked anchors, locked anchors still require at least two eligible safe files, and broad anchors are non-actionable by default unless locked.

Stage 10.5 adds report-only existing organization pattern inference. Existing folders can provide weak local preference evidence for course-code, project, person/student, role, year, or format foldering. Reports can rank related `Needs decision` anchors and show inferred rule candidates, but no rules file is written, no move plans are created directly from inference, and no files move.

Stage 10.6 adds a confirmed organization-rule review workflow. Inferred rule candidates can be exported to manually editable JSON, reviewed as accepted, rejected, ignored, or undecided, and applied to `AI_Review/config/organization_rules.json` only with exact `APPLY ORGANIZATION RULES` confirmation. Rule updates are configuration changes for future reports/grouping only; they do not move files.

Stage 10.7 adds a read-only rule-aware organization audit to JSON and HTML reports. Reports compare conservative defaults with loaded explicit organization rules, show per-rule effects, and warn about broad-impact rules or large suggestion-count increases. The audit does not write rules, create movement-plan items, call `executor.py`, or move files.

Stage 10.8 adds a single-purpose rule-aware organization review export. Existing report organization suggestions are written as deterministic `org-NNNNNN` rows with `approve`, `reject`, or `undecided` decisions and cautious risk labels. The export validates review-file edits but cannot apply rows, construct movement plans, write operation logs, modify organization rules, or move files.

Stage 10.9 adds confirmed apply for approved organization-review rows. Exact `APPLY ORGANIZATION REVIEW` confirmation is checked before the review path is read, duplicate approved paths block the batch, and all filesystem preflight and movement remains in `executor.py`. Apply summaries point to the existing operation log used for undo.

## Stage Summary

- Stage 1: read-only scanner, metadata report, path safety validation, and CLI metadata output.
- Stage 2: exact duplicate detection using SHA-256.
- Stage 3: dry-run duplicate move planning.
- Stage 4: approved duplicate move execution through `executor.py`, operation logs, and undo.
- Stage 5: heuristic review candidates and dry-run review plans.
- Stage 6: deterministic project grouping and dry-run organization plans.
- Stage 7: optional local Ollama group refinement with validated advisory output.
- Stage 7.5: documentation and prompt framework.
- Stage 7.6: documentation audit and pre-Stage-8 safety gate.
- Stage 8: approved deterministic and refined organization moves through `executor.py`.
- Stage 8.5: stabilization docs, manual testing guide, and release notes.
- Stage 9: read-only scheduled-compatible report generation.
- Stage 9.5: report format documentation, sample report, and documentation-only schema reference.
- Stage 10.0: batch CLI review and confirmed bulk apply for approved reviewed-plan items.
- Stage 10.1: apply saved reviewed-plan JSON files after validation and exact confirmation.
- Stage 10.2: review-candidate rows in batch review.
- Stage 10.2.1: reviewed-plan source and destination conflict detection.
- Stage 10.3: persistent review state and organization memory.
- Stage 10.4: automatic static HTML report viewer.
- Stage 10.4.1: conservative organization scope and orphan-code review candidates.
- Stage 10.4.2: protected-context exclusion across actionable plans.
- Stage 10.4.3: strong anchor organization, role-based subfolders, and generated asset suppression.
- Stage 10.4.4: read-only organization rules and anchor-decision reporting.
- Stage 10.5: existing organization pattern inference for JSON and HTML reports.
- Stage 10.6: organization rule candidate export and confirmed rule-decision apply.
- Stage 10.7: rule-aware organization audit in JSON and HTML reports.
- Stage 10.8: read-only rule-aware organization suggestion review export.
- Stage 10.9: confirmed approved organization-review apply through the existing executor.
- Stage 10.10: post-apply verification and undo hardening.
- Stage 10.11: resume and edit saved review sessions.
- Stage 10.12: filtering, sorting, and pagination for review sessions.
- Stage 10.13: confirmed decisions for the current review page.
- Stage 10.14: review-session clarity and unsaved-decision protection.
- Stage 11.0: local web architecture, security, accessibility, and roadmap contract; documentation only.

## Safety Model

- Dry-run is default.
- Real movement requires exact confirmation.
- `executor.py` is the only movement module.
- Every successful move batch writes an operation log.
- Undo uses operation logs and validates paths again.
- Existing destinations are rejected rather than overwritten.
- Movement outside the scan root is rejected.
- Direct symlink sources and unsafe symlink destination parents are rejected.
- Deterministic Python remains the source of truth for facts.
- LLM output is advisory and separately validated.
- Report generation may create a new report file but does not move scanned files.
- HTML report generation may create JSON and HTML report files but does not move scanned files, approve moves, apply moves, write operation logs, or start a server.
- Batch review approve/reject/save commands do not move files.
- Review-candidate rows are candidates for review and use `R` IDs in batch review.
- Reviewed-plan apply is blocked when approved rows conflict on source or destination.
- Reviewed-plan JSON files are review records, not operation logs.
- Review state is decision memory, not an operation log.
- Review state does not record filesystem success and does not replace undo logs.
- Saved reviewed-plan JSON files are untrusted input and are validated before use.
- Normal organization suggestions are document-like by default and exclude code/project/package internals.
- Orphan code is a candidate for review only.
- Protected-context files are excluded from actionable move plans by default.
- Generated web/archive and contextual project-output files are excluded from actionable move plans by default.
- Organization rules are written only by the explicit rule-decision apply flow after exact confirmation.
- Anchor aliases are resolved before reporting; ignored terms win over locked anchors.
- Broad course/name/project/organization anchors are reported for decision instead of becoming concrete organization suggestions by default.
- Existing folder patterns are weak preference evidence in reports only; inferred rule candidates are not written automatically.
- Rule-review apply result logs are configuration-update audit records, not movement operation logs.
- Exact duplicate facts remain distinct from duplicate move candidates.

## Current CLI Capabilities

- Metadata scan: base command and `--max-depth`.
- Duplicate analysis: `--duplicates`, `--plan-duplicates`, `--apply-duplicate-plan`.
- Review candidates: `--review-candidates`, `--plan-review-candidates`.
- Project grouping: `--project-groups`, `--plan-organization`, `--apply-organization-plan`; normal organization suggestions are conservative and document-like by default.
- Local LLM refinement: `--refine-groups`, `--plan-refined-organization`, `--apply-refined-organization-plan`.
- Reports: `--report`, `--report-output <path>`, `--html-report`, `--html-report-output <path>`.
- Organization rule review: `--export-rule-candidates`, `--rule-candidates-output <path>`, `--apply-rule-decisions <path>`.
- Organization suggestion review: `--export-organization-review`, `--organization-review-output <path>`; export and validation only.
- Organization review apply: `--apply-organization-review <path> --confirm "APPLY ORGANIZATION REVIEW"`.
- Batch review: `--review-plans` for duplicate, organization, and review-candidate move candidates.
- Review state bypass: `--review-plans --ignore-review-state`.
- Saved reviewed-plan apply: `--apply-reviewed-plan <path> --confirm APPLY_REVIEWED_PLAN`.
- Undo: `--undo-log <path>`.

Apply commands require one of:

- `--confirm APPLY_DUPLICATE_PLAN`
- `--confirm APPLY_ORGANIZATION_PLAN`
- `--confirm APPLY_REFINED_ORGANIZATION_PLAN`
- interactive `APPLY_REVIEWED_PLAN` inside `--review-plans`
- `--confirm APPLY_REVIEWED_PLAN`
- `--confirm "APPLY ORGANIZATION RULES"`
- `--confirm "APPLY ORGANIZATION REVIEW"`

## Known Limitations

- No built-in scheduler daemon or background service.
- No local web runtime yet; Stage 11.0 defines its architecture and security contract only.
- No HTML report review actions or apply buttons.
- No selective subset or interactive editing command for organization-review files.
- No cloud LLM APIs.
- No path search, arbitrary query syntax, whole-filter/session bulk decisions, or generalized review-file editing.
- Ollama refinement requires a local Ollama service and model.
- Prompt evaluation harness is documented but not implemented.
- Users should inspect dry-run output before approved moves.

## Future Roadmap

See [ROADMAP](ROADMAP.md). Stage 11.5 is the first product-evaluation checkpoint; apply and undo may remain CLI-only while the web review workflow is evaluated.
