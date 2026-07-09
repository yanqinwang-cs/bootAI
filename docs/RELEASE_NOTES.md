# Release Notes

## Current Status Through Stage 10.4.1

Stage 10.4 adds a static HTML report viewer. `--html-report` writes both the existing JSON report and a browser-openable HTML rendering from the same report data without approving or applying moves.

Stage 10.4.1 makes organization conservative by default. Normal organization suggestions are limited to low-risk document-like files, standalone HTML is included only when it does not look like web-project HTML, and isolated code files may be flagged as `orphan_code` candidates for review instead of normal organization suggestions.

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

## Current CLI Capabilities

- Metadata scan: base command and `--max-depth`.
- Duplicate analysis: `--duplicates`, `--plan-duplicates`, `--apply-duplicate-plan`.
- Review candidates: `--review-candidates`, `--plan-review-candidates`.
- Project grouping: `--project-groups`, `--plan-organization`, `--apply-organization-plan`; normal organization suggestions are conservative and document-like by default.
- Local LLM refinement: `--refine-groups`, `--plan-refined-organization`, `--apply-refined-organization-plan`.
- Reports: `--report`, `--report-output <path>`, `--html-report`, `--html-report-output <path>`.
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

## Known Limitations

- No built-in scheduler daemon or background service.
- No GUI yet.
- No HTML report review actions or apply buttons.
- No cloud LLM APIs.
- No filtering/sorting/pagination in batch review yet.
- No saved review-session resume or editing yet.
- Ollama refinement requires a local Ollama service and model.
- Prompt evaluation harness is documented but not implemented.
- Users should inspect dry-run output before approved moves.

## Future Roadmap

See [ROADMAP](ROADMAP.md). Stage 10.5 and later remain future work.
