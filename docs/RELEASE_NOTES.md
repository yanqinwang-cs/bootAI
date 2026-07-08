# Release Notes

## Current Status Through Stage 8.5

Stage 8.5 is a stabilization, manual testing, and release-readiness stage. It adds documentation for safe use and verification. It does not add new runtime behavior.

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

## Current CLI Capabilities

- Metadata scan: base command and `--max-depth`.
- Duplicate analysis: `--duplicates`, `--plan-duplicates`, `--apply-duplicate-plan`.
- Review candidates: `--review-candidates`, `--plan-review-candidates`.
- Project grouping: `--project-groups`, `--plan-organization`, `--apply-organization-plan`.
- Local LLM refinement: `--refine-groups`, `--plan-refined-organization`, `--apply-refined-organization-plan`.
- Undo: `--undo-log <path>`.

Apply commands require one of:

- `--confirm APPLY_DUPLICATE_PLAN`
- `--confirm APPLY_ORGANIZATION_PLAN`
- `--confirm APPLY_REFINED_ORGANIZATION_PLAN`

## Known Limitations

- No scheduled report mode yet.
- No GUI yet.
- No cloud LLM APIs.
- Ollama refinement requires a local Ollama service and model.
- Prompt evaluation harness is documented but not implemented.
- Users should inspect dry-run output before approved moves.

## Future Roadmap

See [ROADMAP](ROADMAP.md). Stage 9 and Stage 10 remain future work.
