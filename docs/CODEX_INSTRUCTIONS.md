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

Stages 1 through 10.5 are complete. Current code supports scanning, duplicate detection, dry-run duplicate plans, approved duplicate moves with logs, review candidates, conservative deterministic grouping for document-like files, orphan-code review candidates, protected/generated/project-output exclusion from actionable plans, strong-anchor organization, read-only organization rules and anchor-decision reporting, report-only existing organization pattern inference, local Ollama refinement, documentation, approved organization moves through `executor.py`, manual testing guidance, release notes, read-only JSON and HTML reports, batch CLI review of duplicate, organization, and review-candidate plans, reviewed-plan conflict detection, persistent review decision memory, and confirmed apply for saved reviewed plans.

## Reuse Before Create

- Before adding a function, check existing modules.
- Before adding a module, check ownership below.
- Do not duplicate safety logic.

## Module Ownership

- `duplicates.py` owns hashing and exact duplicate grouping.
- `review.py` owns heuristic review candidates.
- `scope.py` owns deterministic organization-scope and orphan-code classification helpers only.
- `organization_rules.py` owns read-only organization-rules loading and validation.
- `grouping.py` owns deterministic project grouping.
- `pattern_inference.py` owns report-only inference of existing folder organization patterns.
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
- Stage 10.6 static HTML review export remains future work.
- Stage 10.7 filtering, sorting, and pagination remain future work.
- Stage 10.8 saved-session resume and editing remain future work.

## Testing And Git Hygiene

- Run the full unittest suite before handoff.
- Inspect `git status`, `git diff`, and `git diff --staged` before committing.
- Commit only specific intended files.
- Do not use `git add .` casually.
- Do not add `test_scan/`.
