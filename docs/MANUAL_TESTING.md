# Manual Testing

Use a small disposable folder for manual tests. Do not run apply commands on important folders while testing. Inspect dry-run output before using exact confirmation. Keep operation logs for undo testing.

Run examples from the repository root with:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder
```

## Set Up A Temporary Messy Folder

Create a disposable folder with a few duplicate, project-like, and review-candidate files:

```bash
mkdir -p /path/to/temp-folder/subdir
printf "same" > /path/to/temp-folder/a.txt
printf "same" > /path/to/temp-folder/subdir/b.txt
printf "notes" > /path/to/temp-folder/evosim_notes.txt
printf "report" > /path/to/temp-folder/evosim_report.pdf
printf "" > /path/to/temp-folder/empty_candidate.txt
printf "partial" > /path/to/temp-folder/download.tmp
```

Expected outcome: the folder contains only disposable test data.

## Read-Only Scan

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder
```

Expected outcome: a metadata report is printed and no files move.

## Exact Duplicate Detection

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --duplicates
```

Expected outcome: exact duplicate groups are printed for files with matching content.

## Duplicate Dry-Run Plan

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --plan-duplicates
```

Expected outcome: a dry-run duplicate review plan is printed and no files move.

## Duplicate Apply Refusal Without Confirmation

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-duplicate-plan
```

Expected outcome: the command prints a refusal and no files move.

## Duplicate Apply With Confirmation

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN
```

Expected outcome: approved duplicate move candidates move into `AI_Review/duplicates/`, and an operation log path is printed.

## Duplicate Undo

Use the operation log path printed by the apply command:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --undo-log /path/to/temp-folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

Expected outcome: successful logged duplicate moves are restored.

## Review Candidate Dry-Run

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --plan-review-candidates
```

Expected outcome: review candidates and a dry-run review candidate plan are printed; no files move.

## Project Grouping Dry-Run

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --project-groups
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --plan-organization
```

Expected outcome: suggested groups and a dry-run organization plan are printed; no files move.

## Deterministic Organization Apply Refusal Without Confirmation

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-organization-plan
```

Expected outcome: the command prints a refusal and no files move.

## Deterministic Organization Apply With Confirmation

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Expected outcome: approved organization move candidates move into `Organized/`, and an operation log path is printed.

## Organization Undo

Use the organization apply operation log path:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --undo-log /path/to/temp-folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

Expected outcome: successful logged organization moves are restored.

## Refined Organization Dry-Run

Requires a local Ollama service and model:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
```

Expected outcome: a validated refined dry-run organization plan is printed; no files move.

## Refined Organization Apply Refusal Without Confirmation

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-refined-organization-plan --llm-provider ollama --llm-model qwen2.5:7b
```

Expected outcome: the command prints a refusal and no files move.

## Overwrite Refusal

Before applying an organization plan, create a destination file that matches a planned destination:

```bash
mkdir -p /path/to/temp-folder/Organized/Evosim/notes
printf "existing" > /path/to/temp-folder/Organized/Evosim/notes/evosim_notes.txt
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Expected outcome: the executor rejects the existing destination and does not overwrite it.

## Symlink Refusal

On systems that support symlinks, create a destination parent symlink that points outside the disposable folder, then attempt an organization apply:

```bash
mkdir -p /path/to/outside-folder
ln -s /path/to/outside-folder /path/to/temp-folder/Organized
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Expected outcome: the unsafe destination parent is rejected and files are not moved outside the scan root.

## AI_Review Exclusion

Create a file under `AI_Review/` before planning organization:

```bash
mkdir -p /path/to/temp-folder/AI_Review/notes
printf "reviewed" > /path/to/temp-folder/AI_Review/notes/evosim_hidden.txt
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --plan-organization
```

Expected outcome: files already under `AI_Review/` are not included in organization plans.

## Read-Only Report

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --report
```

Expected outcome: a JSON report file appears under `AI_Review/reports/`, the command prints the report path, and no scanned files move.

## Report Output Inside Root

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --report --report-output /path/to/temp-folder/AI_Review/reports/manual_report.json
```

Expected outcome: the custom report file is created under the scan root.

## Report Output Outside Root Refusal

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --report --report-output /path/to/outside_report.json
```

Expected outcome: the command refuses the path and no report is written outside the scan root.

## Report Overwrite Refusal

Run the same `--report-output` command twice with the same output path.

Expected outcome: the second command refuses to overwrite the existing report.

## Report JSON Review

Open the report JSON and confirm it contains:

- `schema_version`
- `generated_at`
- `scan_root`
- `summary`
- `duplicates`
- `review_candidates`
- `project_groups`
- `organization_suggestions`
- `warnings`

Expected outcome: the report contains facts and suggested dry-run plan items only; it does not approve or apply moves.

## Stage 9.5 Report Format Review

Use a disposable folder and run:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --report
```

Open the generated JSON report and check:

- `schema_version` is present and equals `1`.
- `generated_at` is present.
- `scan_root` is `"."`.
- `summary` contains the expected counts for the disposable folder.
- `duplicates` and `duplicate_review_plan` use relative paths.
- `review_candidates` and `review_candidate_plan` use relative paths.
- `project_groups` and `organization_suggestions` use relative paths.
- `refined_organization_suggestions` is present, even when empty.
- `warnings` is present, even when empty.
- No full file contents or previews are present.
- No scanned files move.

Also confirm:

- The default report path is under `AI_Review/reports/`.
- `--report-output` works for a new path under the scan root.
- `--report-output` refuses a path outside the scan root.
- Reusing the same `--report-output` path refuses to overwrite the first report.
- Apply commands still require exact confirmation and remain separate from reports.

Reference: [REPORT_FORMAT](REPORT_FORMAT.md) and [sample_report.json](examples/sample_report.json).

## Stage 10.4 HTML Report Viewer

Use a disposable folder:

```bash
mkdir -p /path/to/temp-folder/subdir
printf "same" > /path/to/temp-folder/a.txt
printf "same" > /path/to/temp-folder/subdir/b.txt
printf "notes" > /path/to/temp-folder/evosim_notes.txt
printf "report" > /path/to/temp-folder/evosim_report.pdf
printf "" > /path/to/temp-folder/empty_candidate.txt
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report
```

Expected outcome: a JSON report and an HTML report appear under `AI_Review/reports/`, both paths are printed, and no scanned files move.

Open the generated HTML report in a browser and confirm:

- the summary is readable
- warnings are visible when present
- duplicate, review-candidate, project-group, and organization sections are visible
- empty sections show a clear empty message
- there are no approval buttons, apply buttons, or review actions
- no operation log is written

Test a custom HTML output path:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report --html-report-output /path/to/temp-folder/AI_Review/reports/manual_report.html
```

Expected outcome: the custom HTML report is created under the scan root, and a JSON report is still created under `AI_Review/reports/`.

Try incompatible and unsafe commands:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report --review-plans
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report --html-report-output /path/to/outside_report.html
```

Expected outcome: both commands refuse. Reusing the same `--html-report-output` path also refuses to overwrite the existing HTML report.

## Stage 10.0 Batch Review

Use a disposable folder and run:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

In the review session, try:

```text
show duplicates
show organization
reject D1 O1
approve D1
details O1
summary
save
quit
```

Expected outcome: a reviewed-plan JSON file appears under `AI_Review/review_sessions/`, and no files move.

Run review mode again and test wrong confirmation:

```text
apply
WRONG
quit
```

Expected outcome: the command refuses to apply and no files move.

Run review mode again and test confirmed apply:

```text
reject O1
apply
APPLY_REVIEWED_PLAN
```

Expected outcome: only approved move candidates move, rejected move candidates stay in place, and an operation log path is printed.

Use the operation log path:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --undo-log /path/to/temp-folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

Expected outcome: successful logged moves are restored. The reviewed-plan JSON is not an operation log.

## Stage 10.1 Apply Saved Reviewed Plan

Use a disposable folder and run:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

In the review session, reject at least one ID, save the reviewed plan, and quit:

```text
reject O1
save
quit
```

Use the printed reviewed-plan JSON path:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-reviewed-plan /path/to/temp-folder/AI_Review/review_sessions/reviewed_plan.json
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-reviewed-plan /path/to/temp-folder/AI_Review/review_sessions/reviewed_plan.json --confirm WRONG
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --apply-reviewed-plan /path/to/temp-folder/AI_Review/review_sessions/reviewed_plan.json --confirm APPLY_REVIEWED_PLAN
```

Expected outcome: the first two commands refuse to apply and no files move. The confirmed command applies only approved items, leaves rejected items in place, and prints an operation log path.

Then run undo with the operation log path:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --undo-log /path/to/temp-folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

Expected outcome: successful logged moves are restored.

Also edit a copy of the reviewed-plan JSON to make malformed JSON, an absolute source path, or a `../` path. Expected outcome: `--apply-reviewed-plan` refuses the plan. Try a reviewed-plan path outside the scan root; expected outcome: refusal.

## Stage 10.2 Review Candidates In Batch Review

Use a disposable folder with duplicate files, project-like files, temporary files, backup/copy marker files, intentional empty placeholders, and normal files:

```bash
mkdir -p /path/to/temp-folder/subdir
printf "same" > /path/to/temp-folder/a.txt
printf "same" > /path/to/temp-folder/subdir/b.txt
printf "notes" > /path/to/temp-folder/evosim_notes.txt
printf "report" > /path/to/temp-folder/evosim_report.pdf
printf "partial" > /path/to/temp-folder/file.tmp
printf "" > /path/to/temp-folder/empty_candidate.txt
printf "" > /path/to/temp-folder/__init__.py
printf "notes" > /path/to/temp-folder/copywriting_notes.txt
```

Run:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

In the review session, try:

```text
show review-candidates
reject R1
approve R1
details R1
summary
save
apply
WRONG
apply
APPLY_REVIEWED_PLAN
```

Expected outcome: `R` IDs appear for review-candidate move rows only, intentional empty placeholders and copywriting-like names are not review-candidate rows, save writes `review_candidate` items with `review_category` metadata, the wrong confirmation moves nothing, and the exact confirmation applies only approved moves. Approved review-candidate moves go under `AI_Review/<category>/`, and the operation log path can be used with `--undo-log` to restore successful logged moves.

## Stage 10.2.1 Reviewed Plan Conflicts

Use a disposable folder that creates an overlap between duplicate and review-candidate rows:

```bash
printf "" > /path/to/temp-folder/empty_candidate.txt
printf "" > /path/to/temp-folder/.gitkeep
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

In the review session, try:

```text
summary
conflicts
apply
reject <conflicting IDs until one approved move remains for each path>
summary
apply
APPLY_REVIEWED_PLAN
```

Expected outcome: `summary` reports unresolved approved move conflicts, `conflicts` lists the conflicted source or destination rows, and the first `apply` is blocked before confirmation. After rejecting all but one approved move for each conflicted source or destination, exact confirmation is required before any approved move is applied. Saving during a conflict is still allowed and does not move files.

## Stage 10.3 Review State Memory

Use a disposable folder with duplicate files and project-like files:

```bash
mkdir -p /path/to/temp-folder/subdir
printf "same" > /path/to/temp-folder/a.txt
printf "same" > /path/to/temp-folder/subdir/b.txt
printf "notes" > /path/to/temp-folder/evosim_notes.txt
printf "report" > /path/to/temp-folder/evosim_report.pdf
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

In the first review session:

```text
reject D1
save
quit
```

Expected outcome: a reviewed-plan JSON file is written under `AI_Review/review_sessions/`, review decision memory is written under `AI_Review/review_state/review_decisions.json`, no operation log is written, and no files move.

Run review mode again:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans
```

Then try:

```text
show duplicates
summary
quit
```

Expected outcome: matching rows show remembered decision wording, and `summary` includes remembered approval, remembered rejection, new suggestion, and stale prior decision counts.

Run review mode while ignoring memory:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --review-plans --ignore-review-state
```

Expected outcome: rows start from current suggestions, not remembered decisions. The state file is not an operation log and cannot be used with `--undo-log`.

If a source file changes after a decision is remembered, run review mode again. Expected outcome: the row is marked as a stale prior decision and keeps the current default decision until reviewed again.

## Final Git Hygiene Check

From the repository root:

```bash
git status
git diff --name-only
```

Expected outcome: manual test folders such as `test_scan/` are not staged or committed.
