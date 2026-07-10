# Safety Constitution

## Invariants

- Never permanently delete files.
- Never overwrite files.
- Never move outside the selected scan root.
- Always validate paths against the selected scan root.
- Dry-run is the default behavior.
- Exact explicit confirmation is required for apply behavior.
- Every successful move requires an operation log.
- Undo support is required for real movement.
- Direct symlink sources are rejected for moving.
- Unsafe symlink destination parents are rejected.
- Deterministic Python is the source of truth for facts.
- LLM output is advisory only.
- Full file contents are not sent to the LLM by default.
- Planner, review, grouping, and LLM modules must not move files.
- Normal organization suggestions must remain conservative and document-like by default.
- Code/project files must not be broadly organized by default.
- Orphan code is a candidate for review only.
- Report generation must not move files and may only create a new report file.
- HTML report generation must not move files and may only create JSON/HTML report files.
- HTML reports must not approve moves, apply moves, perform review actions, write operation logs, or start a server.
- Review approve/reject/save commands must not move files.
- Review-candidate rows are candidates for review and must not be described as disposal targets.
- Review state records human decisions only.
- Review state is not an operation log and must not be used for undo.
- Remembered decisions must not bypass exact confirmation.
- Failed moves must not become success records in review state.
- Reviewed-plan JSON files are not operation logs.
- A source or destination path must not have multiple approved reviewed-plan moves.
- Reviewed-plan conflicts must block apply until the user rejects conflicting approved rows.
- Saved reviewed-plan JSON files are untrusted input and must be validated before use.
- Resumed reviewed-plan decisions are authoritative and must not be replaced by review-state memory.
- Resume, decision editing, and saving must not scan, regenerate plans, or move files.
- Resumed reviewed-plan saves must not overwrite their input file.
- Review filters, sort order, and pagination are temporary display state only.
- View state must not change decisions, remove hidden rows from saved output, or target rows by page position.
- Rejected saved reviewed-plan items must be ignored for movement.
- Protected-context files are not actionable move candidates by default.
- Generated web/archive assets are not actionable move candidates by default.
- Organization suggestions require strong grouping evidence, not confidence alone.
- Broad course/name/project/organization anchors are non-actionable by default.
- Concrete organization suggestions require narrow repeated document-set evidence or an explicit locked anchor.
- Organization rules are read-only in Stage 10.4.4.
- Existing organization pattern inference is report-only and must not write organization rules.
- Existing folder patterns must not create `MovePlanItem` values directly or approve broad organization.
- Inferred rule candidates are advisory until manually reviewed.
- Rule decisions must not write `organization_rules.json` without exact `APPLY ORGANIZATION RULES` confirmation.
- Rule-review config updates must not create `MovePlanItem` values, call `executor.py`, move files, or write movement operation logs.
- `preferred_granularities` are advisory only in Stage 10.6.
- Rule-aware audit is read-only and must not write or modify organization rules.
- Rule-aware audit must not create movement-plan items, call `executor.py`, move files, or write operation logs.
- Preferred granularities remain advisory and non-behavior-changing in Stage 10.7.
- Organization-review export may write a new JSON review file but must not create execution-ready movement plans or apply reviewed rows.
- Organization-review destinations must be safe relative paths under the controlled `Organized/` output namespace; they do not need to exist during review.
- Organization-review decisions remain review metadata and must not bypass a later separately designed confirmation and validation stage.
- Organization-review apply requires exact `APPLY ORGANIZATION REVIEW` confirmation before the review path is read or validated.
- Only approved organization-review rows may become `MovePlanItem` values; rejected and undecided rows remain summary metadata.
- Duplicate approved sources or destinations must block organization-review apply before executor use.
- Organization-review apply-result files do not replace executor operation logs; undo continues to use operation logs.
- Organization apply verification reports are audit records, not operation logs, and cannot trigger movement or undo.
- Verification inputs must be regular non-symlink files under the selected root.
- Locked anchors must not bypass protected/generated/project-output exclusions.
- Locked anchors should require at least two eligible safe files before producing organization suggestions.
- Ignored terms win over locked anchors after alias normalization.
- Exact duplicate facts must remain distinct from duplicate move candidates.
- Batch review apply requires exact `APPLY_REVIEWED_PLAN` confirmation.
- `executor.py` is the only movement module.
- Approved duplicate, organization, and review-candidate moves all use `executor.py`.
- Organization apply requires exact confirmation and keeps dry-run planning as the default.

## Risk Categories

- Exact duplicates: files with matching SHA-256 hashes.
- Empty files: candidate for review unless they are known placeholders.
- Temporary files: candidate for review when filename patterns match system or temporary artifacts.
- Backup or copy files: candidate for review when filename tokens indicate version markers.
- Project organization candidates: suggested groups based on deterministic course-code or token signals.
- Orphan code: isolated code files outside detected project contexts, surfaced only as candidates for review.
- Protected contexts: dependency folders, Git internals, virtual environments, app/framework bundles, protected workspaces, and project/package contexts excluded from actionable plans.
- Generated asset contexts: browser-saved asset folders, generated web assets, and contextual project-output folders excluded from actionable plans.

## Language Rules

Use cautious language: `candidate for review`, `suggested`, `dry-run`, `approved move`, and `operation log`. Avoid claims that imply disposal, automatic action, or certainty beyond the deterministic facts.

Do not use these phrases except when listing forbidden wording:

- `safe to delete`
- `useless`
- `automatic cleanup`
- `permanent cleanup`
