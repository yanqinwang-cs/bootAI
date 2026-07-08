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

Only `--apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN` can move files today.

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

## Grouping

```bash
python -m organizer.cli <folder> --project-groups
python -m organizer.cli <folder> --plan-organization
```

- `--project-groups`: read-only; prints suggested groups.
- `--plan-organization`: dry-run; prints an organization plan.

Organization plans are not applied in Stage 7.6. No Stage 8 organization apply flags exist yet.

## LLM Refinement

```bash
python -m organizer.cli <folder> --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
python -m organizer.cli <folder> --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b --ollama-host http://localhost:11434
```

- `--refine-groups`: LLM-assisted; prints advisory local Ollama refinements.
- `--plan-refined-organization`: LLM-assisted dry-run; prints a refined organization plan.
- `--llm-provider ollama`: LLM-assisted; required for refinement commands.
- `--llm-model <model>`: LLM-assisted; required for refinement commands.
- `--ollama-host <url>`: LLM-assisted; optional local Ollama host override.

LLM refinement is optional and local-only. Refined organization plans are dry-run only.
