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

Prints a metadata report. Read-only.

## Duplicate Commands

```bash
python -m organizer.cli <folder> --duplicates
python -m organizer.cli <folder> --plan-duplicates
python -m organizer.cli <folder> --apply-duplicate-plan
python -m organizer.cli <folder> --apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN
```

- `--duplicates`: prints exact duplicate groups. Read-only.
- `--plan-duplicates`: prints a dry-run duplicate review plan.
- `--apply-duplicate-plan`: prints the plan and refuses to apply without exact confirmation.
- `--confirm APPLY_DUPLICATE_PLAN`: required for the current approved duplicate move command.

Only `--apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN` can move files today.

## Undo

```bash
python -m organizer.cli <folder> --undo-log <path>
```

Restores successful entries from an operation log when validation passes.

## Review Candidates

```bash
python -m organizer.cli <folder> --review-candidates
python -m organizer.cli <folder> --plan-review-candidates
```

Prints heuristic candidates for review or a dry-run review candidate plan. Read-only.

## Grouping

```bash
python -m organizer.cli <folder> --project-groups
python -m organizer.cli <folder> --plan-organization
```

Prints suggested groups or a dry-run organization plan. Organization plans are not applied in Stage 7.5.

## LLM Refinement

```bash
python -m organizer.cli <folder> --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b --ollama-host http://localhost:11434
```

LLM refinement is optional and local-only. Refined organization plans are dry-run only.
