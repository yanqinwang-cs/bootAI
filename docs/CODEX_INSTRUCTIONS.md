# Codex Instructions

Codex must read this file before implementing future stages.

## Before Editing

- Use Plan Mode before editing.
- State the requested stage.
- State explicit non-goals.
- List intended files before editing.
- Inspect existing modules before adding code.
- Reuse existing functions where possible.
- Respect module ownership.
- Do not skip ahead.
- Do not duplicate existing subsystems.
- Do not touch `test_scan/`.

## Completed Stages

Stages 1 through 10.12 are complete. Current code supports scanning, duplicate detection, dry-run duplicate plans, approved duplicate moves with logs, review candidates, conservative deterministic grouping for document-like files, orphan-code review candidates, protected/generated/project-output exclusion from actionable plans, strong-anchor organization, organization rules and anchor-decision reporting, report-only existing organization pattern inference, confirmed organization-rule review, rule-aware organization audit, rule-aware organization review JSON export, confirmed approved organization-review apply, read-only post-apply verification, saved review-session resume and editing, temporary review filtering/sorting/pagination, local Ollama refinement, documentation, approved organization moves through `executor.py`, manual testing guidance, release notes, read-only JSON and HTML reports, batch CLI review of duplicate, organization, and review-candidate plans, reviewed-plan conflict detection, persistent review decision memory, and confirmed apply for saved reviewed plans.

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
- `html_report.py` owns read-only static HTML rendering from report dictionaries.
- `review_session.py` owns batch review-session construction, decisions, reviewed-plan JSON writing, saved-plan validation, and conversion back to `MovePlanItem` values.
- `review_state.py` owns persistent human review decision memory.
- `executor.py` owns moving and undo.

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
- Bulk decisions on visible rows and richer review interfaces remain future work.

## Testing And Git Hygiene

- Run the full unittest suite before handoff.
- Inspect `git status`, `git diff`, and `git diff --staged` before committing.
- Commit only specific intended files.
- Do not use `git add .` casually.
- Do not add `test_scan/`.
