# CLI Reference

Run commands with:

```bash
PYTHONPATH=src python -m organizer.cli <folder>
```

## Base

```bash
python -m organizer.cli <folder>
python -m organizer.cli <folder> --max-depth 2
```

Category: read-only.

Prints a metadata report.

## Duplicate Commands

```bash
python -m organizer.cli <folder> --duplicates
python -m organizer.cli <folder> --plan-duplicates
python -m organizer.cli <folder> --apply-duplicate-plan
python -m organizer.cli <folder> --apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN
```

- `--duplicates`: read-only; prints exact duplicate groups.
- `--plan-duplicates`: dry-run; prints a duplicate review plan.
- `--apply-duplicate-plan`: apply; prints the plan and refuses to apply without exact confirmation.
- `--confirm APPLY_DUPLICATE_PLAN`: apply; required for the current approved duplicate move command.

Duplicate review moves require `--apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN`. Organization moves have separate exact confirmation strings below.

## Undo

```bash
python -m organizer.cli <folder> --undo-log <path>
```

Category: undo.

Restores successful entries from an operation log when validation passes.

## Review Candidates

```bash
python -m organizer.cli <folder> --review-candidates
python -m organizer.cli <folder> --plan-review-candidates
```

- `--review-candidates`: read-only; prints heuristic candidates for review.
- `--plan-review-candidates`: dry-run; prints a review candidate plan.

## Reports

```bash
python -m organizer.cli <folder> --report
python -m organizer.cli <folder> --report --max-depth 2
python -m organizer.cli <folder> --report --report-output <path-under-folder>
python -m organizer.cli <folder> --report --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --html-report
python -m organizer.cli <folder> --html-report --html-report-output <path-under-folder>
python -m organizer.cli <folder> --html-report --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
```

- `--report`: read-only; writes a JSON report and prints the report path.
- `--report-output <path>`: read-only; writes the report to a specific path under the scan root.
- `--html-report`: read-only; writes a JSON report and a static HTML report viewer.
- `--html-report-output <path>`: read-only; writes the HTML report to a specific path under the scan root.
- `--refine-groups`: optional local LLM-assisted report section when combined with `--report` or `--html-report`, `--llm-provider ollama`, and `--llm-model <model>`.

Report mode is single-purpose. It rejects display, planning, apply, undo, and confirmation flags to avoid ambiguous output. It writes a report file only; it does not move scanned files, approve moves, or apply moves. `--report-output` must point under the scan root and must not already exist.

HTML report mode is also single-purpose. It writes both JSON and HTML reports from the same in-memory report data, rejects display, planning, apply, review, undo, report, and confirmation flags, and does not start a server. The HTML report is a browser-openable static viewer only. It has no approval buttons, apply buttons, or review actions, and it does not write operation logs. `--html-report-output` must point under the scan root and must not already exist.

The report format is documented in [REPORT_FORMAT](REPORT_FORMAT.md). A compact example is available at [sample_report.json](examples/sample_report.json).

## Grouping

```bash
python -m organizer.cli <folder> --project-groups
python -m organizer.cli <folder> --plan-organization
python -m organizer.cli <folder> --apply-organization-plan
python -m organizer.cli <folder> --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

- `--project-groups`: read-only; prints suggested groups.
- `--plan-organization`: dry-run; prints an organization plan.
- `--apply-organization-plan`: apply; prints the dry-run organization plan and refuses to apply without exact confirmation.
- `--confirm APPLY_ORGANIZATION_PLAN`: apply; required for approved deterministic organization moves.

Only `--apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN` can apply deterministic organization moves. The move batch writes an operation log under `AI_Review/operation_logs` and can be undone with `--undo-log`.

## LLM Refinement

```bash
python -m organizer.cli <folder> --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b --ollama-host http://localhost:11434
python -m organizer.cli <folder> --apply-refined-organization-plan --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --apply-refined-organization-plan --llm-provider ollama --llm-model qwen2.5:7b --confirm APPLY_REFINED_ORGANIZATION_PLAN
```

- `--refine-groups`: LLM-assisted; prints advisory local Ollama refinements.
- `--plan-refined-organization`: LLM-assisted dry-run; prints a refined organization plan.
- `--apply-refined-organization-plan`: LLM-assisted apply; prints the dry-run refined organization plan and refuses to apply without exact confirmation.
- `--llm-provider ollama`: LLM-assisted; required for refinement commands.
- `--llm-model <model>`: LLM-assisted; required for refinement commands.
- `--ollama-host <url>`: LLM-assisted; optional local Ollama host override.
- `--confirm APPLY_REFINED_ORGANIZATION_PLAN`: apply; required for approved refined organization moves.

LLM refinement is optional and local-only. Refined organization apply still uses validated Python `MovePlanItem` values and `executor.py`.

## Batch Review

```bash
python -m organizer.cli <folder> --review-plans
python -m organizer.cli <folder> --review-plans --max-depth 2
python -m organizer.cli <folder> --review-plans --ignore-review-state
python -m organizer.cli <folder> --apply-reviewed-plan AI_Review/review_sessions/<plan>.json --confirm APPLY_REVIEWED_PLAN
```

- `--review-plans`: interactive batch review for duplicate, deterministic organization, and review-candidate move candidates.
- `--ignore-review-state`: review mode only; starts from current suggestions without applying remembered review decisions.
- `--apply-reviewed-plan <path>`: apply approved items from a saved reviewed-plan JSON file after validation and exact confirmation.

Review mode is single-purpose. It rejects display, planning, apply, undo, report, LLM, and confirmation flags. It allows `--max-depth` and `--ignore-review-state`.

Inside the review session:

- `help`: show commands.
- `show duplicates`: show duplicate suggested moves.
- `show organization`: show organization suggested moves.
- `show review-candidates`: show review-candidate suggested moves with `R` IDs.
- `summary`: show approved and rejected move counts.
- `conflicts`: show approved source and destination conflicts.
- `reject <IDs...>`: mark suggested moves as rejected.
- `approve <IDs...>`: mark rejected moves as approved again.
- `details <ID>`: show full details for one item.
- `save`: write a reviewed-plan JSON file under `AI_Review/review_sessions/`.
- `apply`: save the current reviewed plan if needed, then require exact `APPLY_REVIEWED_PLAN` confirmation before applying approved moves.
- `quit`: exit without applying.

By default, `--review-plans` loads review decision memory from `AI_Review/review_state/review_decisions.json`. Matching rows can be pre-marked as remembered approvals or remembered rejections, and stale prior decisions are shown when the source path still matches but file size or modified time changed. `--ignore-review-state` skips this memory for the current session. Review state is decision memory only. It is not an operation log, does not record filesystem success, and does not replace undo logs.

Approve, reject, and save commands do not move files. `save` writes both a reviewed-plan JSON record and review-state decision memory. Review-candidate rows are candidates for review, use `R` IDs, and keep `category = "review_candidate"` separate from the review candidate category such as `temporary`, `empty`, or `backup_or_copy`. If one source or destination path has multiple approved moves, `summary` reports the conflict count and `apply` is blocked until the conflict is resolved. Resolve a source conflict by rejecting all but one approved move for that source. Resolve a destination conflict by rejecting all but one approved move targeting that destination. Only `apply` with exact `APPLY_REVIEWED_PLAN` confirmation can move approved files, and movement still goes through `executor.py`. Reviewed-plan JSON files are review records, not operation logs. Undo uses the operation log printed after a real apply.

Interactive apply may update review-state memory after exact confirmation and before executor apply. That state records review intent only. Operation logs remain authoritative for actual successful moves and undo, and failed moves do not become success records in review state.

Saved reviewed plans are untrusted input. `--apply-reviewed-plan` validates the plan path under the scan root, checks the JSON shape, rejects absolute paths and path traversal, ignores rejected items, blocks approved move conflicts, and converts only approved items back into `MovePlanItem` values. It does not resume or edit review sessions.
