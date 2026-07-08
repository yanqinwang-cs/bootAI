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

## Final Git Hygiene Check

From the repository root:

```bash
git status
git diff --name-only
```

Expected outcome: manual test folders such as `test_scan/` are not staged or committed.
