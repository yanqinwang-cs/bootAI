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

Exact duplicate groups are factual. Duplicate review plans are actionable candidates and exclude protected contexts such as dependency folders, Git internals, virtual environments, app/framework bundles, protected workspaces, and project/package contexts by default.

Generated web/archive assets and contextual project-output paths are also excluded from actionable duplicate review plans by default.

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

Reports include read-only organization-rules status and alias-normalized anchor decisions. If `AI_Review/config/organization_rules.json` exists, it is loaded for reporting and grouping decisions. If it is missing, conservative built-in defaults are used. The CLI does not create or edit this rules file.

Reports also include existing organization pattern inference. This is report-only
weak preference evidence from existing eligible folders. It can rank
`Needs decision` anchors and suggest manual rule candidates, but it does not
write rules, create move plans directly, or apply moves.

## Organization Rule Review

```bash
python -m organizer.cli <folder> --export-rule-candidates
python -m organizer.cli <folder> --export-rule-candidates --rule-candidates-output AI_Review/rules/manual_candidates.json
python -m organizer.cli <folder> --apply-rule-decisions AI_Review/rules/organization_rule_candidates.reviewed.json --confirm "APPLY ORGANIZATION RULES"
```

- `--export-rule-candidates`: scans read-only and writes a manually reviewable JSON file under `AI_Review/rules/`.
- `--rule-candidates-output <path>`: writes exported candidates to a specific new path under the scan root.
- `--apply-rule-decisions <path>`: validates a reviewed candidate file and applies accepted decisions to `AI_Review/config/organization_rules.json`.
- `--confirm "APPLY ORGANIZATION RULES"`: required exactly before any organization-rules file is written.

Candidate export is advisory and does not write `organization_rules.json`. If the default candidate output already exists, export writes a collision-safe sibling rather than overwriting it. A custom output path must not already exist.

Applying rule decisions treats the reviewed JSON file as the source of truth. It does not rescan, infer new candidates, create move plans, call the executor, move files, or write operation logs. Rejected, ignored, and undecided candidates are recorded in the apply result log but do not update rules. `preferred_granularities` are stored as advisory configuration only in this stage.

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

Organization suggestions are conservative by default. Eligible normal organization files are `.pdf`, `.md`, `.markdown`, `.txt`, `.rtf`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.html`, and `.htm`. HTML files are suggested only when they look like standalone documents, not web-project internals. Code, package, app, framework, dependency, archive, media, and project-context files are excluded from normal organization suggestions. Isolated code may appear as an `orphan_code` candidate for review instead.

Organization groups require narrow repeated document-set evidence or an explicit locked anchor. Broad anchors such as course/module codes, project names, personal names, and organization-like terms are reported as needing a decision by default. Weak tokens such as `summary`, `report`, `resource`, `index`, `image`, `balanced`, `v1`, and `debug` do not create top-level organization suggestions by default. Role-based subfolders such as `exams`, `recitations`, `lectures`, `practicals`, `slides`, and `notes` are assigned after grouping.

Optional read-only organization rules can be provided manually at `AI_Review/config/organization_rules.json` with `version`, `locked_anchors`, `ignored_terms`, and `anchor_aliases`. Aliases are resolved before anchor decisions are shown, ignored terms win over locked anchors, and locked anchors still require at least two eligible safe files. No CLI command initializes or edits the rules file in this stage.

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

Approve, reject, and save commands do not move files. `save` writes both a reviewed-plan JSON record and review-state decision memory. Review-candidate rows are candidates for review, use `R` IDs, and keep `category = "review_candidate"` separate from the review candidate category such as `temporary`, `empty`, `backup_or_copy`, or `orphan_code`. If one source or destination path has multiple approved moves, `summary` reports the conflict count and `apply` is blocked until the conflict is resolved. Resolve a source conflict by rejecting all but one approved move for that source. Resolve a destination conflict by rejecting all but one approved move targeting that destination. Only `apply` with exact `APPLY_REVIEWED_PLAN` confirmation can move approved files, and movement still goes through `executor.py`. Reviewed-plan JSON files are review records, not operation logs. Undo uses the operation log printed after a real apply.

Interactive apply may update review-state memory after exact confirmation and before executor apply. That state records review intent only. Operation logs remain authoritative for actual successful moves and undo, and failed moves do not become success records in review state.

Saved reviewed plans are untrusted input. `--apply-reviewed-plan` validates the plan path under the scan root, checks the JSON shape, rejects absolute paths and path traversal, ignores rejected items, blocks approved move conflicts, and converts only approved items back into `MovePlanItem` values. It does not resume or edit review sessions.

Approved saved reviewed-plan items involving protected-context sources are rejected before executor use. Tool-owned destinations under `AI_Review/` and `Organized/` remain valid reviewed-plan destinations.
