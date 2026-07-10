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

## Stage 10.4.1 Conservative Scope Check

Use a disposable folder:

```bash
mkdir -p /path/to/temp-folder/web_project
mkdir -p /path/to/temp-folder/project
mkdir -p /path/to/temp-folder/Fake.app/Contents/Resources
printf "notes" > /path/to/temp-folder/course_notes.pdf
printf "notes" > /path/to/temp-folder/course_notes.md
printf "notes" > /path/to/temp-folder/course_notes.txt
printf "doc" > /path/to/temp-folder/course_notes.docx
printf "slides" > /path/to/temp-folder/course_notes.pptx
printf "<html>article</html>" > /path/to/temp-folder/article.html
printf "<html>app</html>" > /path/to/temp-folder/web_project/index.html
printf "body{}" > /path/to/temp-folder/web_project/style.css
printf "console.log('app')" > /path/to/temp-folder/web_project/app.js
printf "{}" > /path/to/temp-folder/web_project/package.json
printf "print('practice')" > /path/to/temp-folder/practice.py
printf "[project]" > /path/to/temp-folder/project/pyproject.toml
printf "print('project')" > /path/to/temp-folder/project/app.py
printf "app data" > /path/to/temp-folder/Fake.app/Contents/Resources/file.txt
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report
```

Expected outcome: normal organization suggestions mostly include document-like files, standalone `article.html` can be suggested, web-project HTML is excluded, code/project files are not normal organization suggestions, isolated `practice.py` appears as an `orphan_code` candidate for review, project code does not appear as `orphan_code`, and no files move.

## Stage 10.4.2 Protected Context Actionable-Plan Check

Use a disposable folder:

```bash
mkdir -p /path/to/temp-folder/node_modules/pkg
mkdir -p /path/to/temp-folder/FakeApp.app/Contents
printf "same-pdf" > /path/to/temp-folder/a.pdf
printf "same-pdf" > /path/to/temp-folder/b.pdf
printf "same-js" > /path/to/temp-folder/node_modules/pkg/a.js
printf "same-js" > /path/to/temp-folder/node_modules/pkg/b.js
printf "same-app" > /path/to/temp-folder/FakeApp.app/Contents/a.txt
printf "same-app" > /path/to/temp-folder/FakeApp.app/Contents/b.txt
printf "temp" > /path/to/temp-folder/node_modules/pkg/file.tmp
printf "print('practice')" > /path/to/temp-folder/practice.py
PYTHONPATH=src python3 -m organizer.cli /path/to/temp-folder --html-report
```

Expected outcome: exact duplicate facts may include protected duplicates, duplicate review plan entries exclude `node_modules/` and `.app` paths, review candidate plans exclude protected contexts, ordinary duplicate PDFs still appear as duplicate review candidates, isolated `practice.py` still appears as an `orphan_code` candidate for review, and no files move.

## Stage 10.4.3 Strong Anchor And Generated Asset Check

Use a disposable folder:

```bash
SMOKE_ROOT="/tmp/bootai_anchor_smoke"
rm -rf "$SMOKE_ROOT"
mkdir -p "$SMOKE_ROOT/Instagram_files"
mkdir -p "$SMOKE_ROOT/SomePage_files"
mkdir -p "$SMOKE_ROOT/project/resources"
mkdir -p "$SMOKE_ROOT/project/src"

printf "x\n" > "$SMOKE_ROOT/CS1010X practical exam 2025 questions.pdf"
printf "x\n" > "$SMOKE_ROOT/CS1010X finals 2026.pdf"
printf "x\n" > "$SMOKE_ROOT/CS1010X recitation 04.pdf"
printf "x\n" > "$SMOKE_ROOT/CS1010X-lec12-Object-Oriented Programming.ppt"
printf "x\n" > "$SMOKE_ROOT/summary_one.pdf"
printf "x\n" > "$SMOKE_ROOT/summary_two.pdf"
printf "console.log(1)\n" > "$SMOKE_ROOT/Instagram_files/base.js"
printf "body{}\n" > "$SMOKE_ROOT/SomePage_files/style.css"
printf "print('hi')\n" > "$SMOKE_ROOT/practice.py"
printf "asset\n" > "$SMOKE_ROOT/project/resources/icon.png"
printf "print('project')\n" > "$SMOKE_ROOT/project/src/main.py"

PYTHONPATH=src python3 -m organizer.cli "$SMOKE_ROOT" --html-report
```

Expected outcome: broad `CS1010X` appears under anchors needing a decision, concrete narrow sets such as finals or recitations may appear as organization groups with role-based subfolders, weak `summary` files do not create a top-level organization group, generated web assets do not appear as `orphan_code`, contextual project-output files are not actionable candidates, loose `practice.py` appears as an `orphan_code` candidate for review, and no files move.

## Stage 10.4.4 Read-Only Organization Rules Check

Use a disposable folder and create the optional rules file manually:

```bash
RULE_ROOT="/tmp/bootai_rules_smoke"
rm -rf "$RULE_ROOT"
mkdir -p "$RULE_ROOT/AI_Review/config"

cat > "$RULE_ROOT/AI_Review/config/organization_rules.json" <<'JSON'
{
  "version": 1,
  "locked_anchors": ["Misc"],
  "ignored_terms": ["EvoSim"],
  "anchor_aliases": {
    "CS1010x": "CS1010X"
  }
}
JSON

printf "x\n" > "$RULE_ROOT/misc_notes.txt"
printf "x\n" > "$RULE_ROOT/misc_report.pdf"
printf "x\n" > "$RULE_ROOT/evosim_notes.txt"
printf "x\n" > "$RULE_ROOT/evosim_report.pdf"
printf "x\n" > "$RULE_ROOT/CS1010x notes.pdf"
printf "x\n" > "$RULE_ROOT/CS1010X slides.pptx"

PYTHONPATH=src python3 -m organizer.cli "$RULE_ROOT" --html-report
```

Expected outcome: the report says organization rules were loaded, `Misc` appears as a suggested group because it has two eligible safe files, `EvoSim` appears under ignored terms and does not produce organization plan items, and aliased `CS1010x`/`CS1010X` is shown as one final anchor decision. No files move, and the CLI does not create or edit the rules file.

## Stage 10.6 Organization Rule Review Check

Use a disposable folder:

```bash
RULE_ROOT="/tmp/bootai_rule_review_smoke"
rm -rf "$RULE_ROOT"
mkdir -p "$RULE_ROOT/cs1010x finals" "$RULE_ROOT/EvoSim images" "$RULE_ROOT/ourdream"

printf "x\n" > "$RULE_ROOT/cs1010x finals/cs1010x-final-jun21.pdf"
printf "x\n" > "$RULE_ROOT/cs1010x finals/cs1010x-final-solutions-jun21.pdf"
printf "x\n" > "$RULE_ROOT/EvoSim images/EvoSim_project_slides.pptx"
printf "x\n" > "$RULE_ROOT/EvoSim images/EvoSim_fixed_google_slides.pptx"
printf "x\n" > "$RULE_ROOT/ourdream/OurDream_Character_Guide.pdf"
printf "x\n" > "$RULE_ROOT/ourdream/OurDream_Image_Generation_Rules_v2.md"

PYTHONPATH=src python3 -m organizer.cli "$RULE_ROOT" --export-rule-candidates
```

Expected outcome: `AI_Review/rules/organization_rule_candidates.json` exists, candidates have `decision: "undecided"`, and `AI_Review/config/organization_rules.json` does not exist.

Copy and edit the candidate file, setting a small number of selected `decision` fields to `accept`:

```bash
cp "$RULE_ROOT/AI_Review/rules/organization_rule_candidates.json" \
  "$RULE_ROOT/AI_Review/rules/organization_rule_candidates.reviewed.json"
```

Wrong confirmation should refuse:

```bash
PYTHONPATH=src python3 -m organizer.cli "$RULE_ROOT" \
  --apply-rule-decisions "$RULE_ROOT/AI_Review/rules/organization_rule_candidates.reviewed.json" \
  --confirm "WRONG"
```

Exact confirmation can update rules:

```bash
PYTHONPATH=src python3 -m organizer.cli "$RULE_ROOT" \
  --apply-rule-decisions "$RULE_ROOT/AI_Review/rules/organization_rule_candidates.reviewed.json" \
  --confirm "APPLY ORGANIZATION RULES"
```

Expected outcome: only accepted rule decisions are written to `AI_Review/config/organization_rules.json`, a rule apply result log is written under `AI_Review/rules/`, and no files move.

## Stage 10.7 Rule-Aware Audit Check

Use a disposable folder:

```bash
AUDIT_ROOT="/tmp/bootai_rule_audit_smoke"
rm -rf "$AUDIT_ROOT"
mkdir -p "$AUDIT_ROOT/AI_Review/config"

cat > "$AUDIT_ROOT/AI_Review/config/organization_rules.json" <<'JSON'
{
  "version": 1,
  "locked_anchors": ["CS1010X"],
  "ignored_terms": ["Python"],
  "anchor_aliases": {
    "programming methodology": "CS1010X"
  },
  "preferred_granularities": ["course_code"]
}
JSON

printf "x\n" > "$AUDIT_ROOT/CS1010X-lec1.pdf"
printf "x\n" > "$AUDIT_ROOT/CS1010X-lec2.pdf"
printf "x\n" > "$AUDIT_ROOT/Python notes.pdf"
printf "x\n" > "$AUDIT_ROOT/Python slides.pdf"

PYTHONPATH=src python3 -m organizer.cli "$AUDIT_ROOT" --html-report
```

Expected outcome: JSON and HTML reports include `rule_audit`, `rules_loaded` is true, locked anchors and ignored terms are listed, per-rule effects are shown, preferred granularities are described as advisory, `organization_rules.json` is unchanged, and no files move.

No-rules check:

```bash
AUDIT_ROOT="/tmp/bootai_rule_audit_no_rules_smoke"
rm -rf "$AUDIT_ROOT"
mkdir -p "$AUDIT_ROOT"
printf "x\n" > "$AUDIT_ROOT/CS1010X-lec1.pdf"

PYTHONPATH=src python3 -m organizer.cli "$AUDIT_ROOT" --html-report
test ! -f "$AUDIT_ROOT/AI_Review/config/organization_rules.json" && echo "OK: report did not create rules"
```

## Stage 10.8 Organization Review Export Check

Use a disposable folder:

```bash
REVIEW_ROOT="/tmp/bootai_organization_review_smoke"
rm -rf "$REVIEW_ROOT"
mkdir -p "$REVIEW_ROOT/AI_Review/config"

cat > "$REVIEW_ROOT/AI_Review/config/organization_rules.json" <<'JSON'
{
  "version": 1,
  "locked_anchors": ["CS1010X"],
  "preferred_granularities": ["course_code"]
}
JSON

printf "one\n" > "$REVIEW_ROOT/CS1010X lecture 01.pdf"
printf "two\n" > "$REVIEW_ROOT/CS1010X lecture 02.pdf"

PYTHONPATH=src python3 -m organizer.cli "$REVIEW_ROOT" \
  --export-organization-review
```

Expected outcome: `AI_Review/reviews/organization_review.json` exists, every row starts with `decision: "undecided"` and an empty note, destinations are relative under `Organized/`, and the rule audit summary lists `CS1010X` and advisory preferred granularities. No source file moves, no operation log is written, and `organization_rules.json` is unchanged.

Run the same command again. Expected outcome: `organization_review_1.json` is created and the first file is unchanged. Then verify an explicit collision is refused:

```bash
PYTHONPATH=src python3 -m organizer.cli "$REVIEW_ROOT" \
  --export-organization-review \
  --organization-review-output AI_Review/reviews/organization_review.json
```

Edit a copy manually and set selected rows to `approve`, `reject`, or `undecided`. The Stage 10.8 export command itself remains non-mutating.

## Stage 10.9 Approved Organization Review Apply Check

Continue only in the disposable Stage 10.8 folder. Copy the export and manually approve one or two rows:

```bash
cp "$REVIEW_ROOT/AI_Review/reviews/organization_review.json" \
  "$REVIEW_ROOT/AI_Review/reviews/organization_review.approved.json"
```

First use incorrect confirmation:

```bash
PYTHONPATH=src python3 -m organizer.cli "$REVIEW_ROOT" \
  --apply-organization-review AI_Review/reviews/organization_review.approved.json \
  --confirm "WRONG"
```

Expected outcome: the CLI refuses before reading the review file, no files move, no operation log exists, and no apply-result JSON is written.

After inspecting the approved rows, use exact confirmation:

```bash
PYTHONPATH=src python3 -m organizer.cli "$REVIEW_ROOT" \
  --apply-organization-review AI_Review/reviews/organization_review.approved.json \
  --confirm "APPLY ORGANIZATION REVIEW"
```

Expected outcome: only approved rows move under `Organized/`; rejected and undecided rows remain in place. The CLI prints an apply-result path and an executor operation-log path. Use that operation log with the existing `--undo-log` command and confirm the moved files return to their original paths. Repeat only with newly recreated source files; apply-result filenames must use collision-safe siblings rather than overwrite earlier summaries.

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

## Stage 10.5 Existing Organization Pattern Inference

Use a disposable folder:

```bash
SMOKE_ROOT="/tmp/bootai_pattern_inference_smoke"
rm -rf "$SMOKE_ROOT"
mkdir -p "$SMOKE_ROOT/CS1010X"
mkdir -p "$SMOKE_ROOT/Submissions/Wang"
mkdir -p "$SMOKE_ROOT/Submissions/Tan"

printf "x\n" > "$SMOKE_ROOT/CS1010X/CS1010X finals.pdf"
printf "x\n" > "$SMOKE_ROOT/CS1010X/CS1010X recitation 01.pdf"
printf "x\n" > "$SMOKE_ROOT/CS2020 finals.pdf"
printf "x\n" > "$SMOKE_ROOT/CS2020 recitation 01.pdf"
printf "x\n" > "$SMOKE_ROOT/Submissions/Wang/assignment 1.pdf"
printf "x\n" > "$SMOKE_ROOT/Submissions/Wang/assignment 2.pdf"
printf "x\n" > "$SMOKE_ROOT/Submissions/Tan/assignment 1.pdf"
printf "x\n" > "$SMOKE_ROOT/Submissions/Tan/assignment 2.pdf"
printf "x\n" > "$SMOKE_ROOT/Aisha assignment 1.pdf"
printf "x\n" > "$SMOKE_ROOT/Aisha assignment 2.pdf"

PYTHONPATH=src python3 -m organizer.cli "$SMOKE_ROOT" --html-report
```

Expected outcome: the HTML report includes `Inferred organization patterns`,
course-code foldering, and person/student foldering. `CS2020` appears as a
needs-decision anchor with course-code pattern evidence, and `Aisha` appears as
a needs-decision anchor with person/student pattern evidence. The command writes
report files only, does not create `AI_Review/config/organization_rules.json`,
and does not move scanned files.

## Final Git Hygiene Check

From the repository root:

```bash
git status
git diff --name-only
```

Expected outcome: manual test folders such as `test_scan/` are not staged or committed.
