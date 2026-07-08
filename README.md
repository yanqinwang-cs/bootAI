# bootAI

`bootAI` is a cautious local file organizer for scanning folders, reviewing metadata, and applying explicitly approved move plans.

The project is safety-first: dry-run is default, real movement requires exact confirmation, the tool never permanently deletes files by default, the tool never overwrites files, and all real movement goes through approved move plans and operation logs.

## Current Status

Stages 1 through 8 are implemented. The tool can currently:

- Scan folders read-only.
- Detect exact duplicates with SHA-256.
- Build duplicate review plans.
- Apply approved duplicate review moves with undo logs.
- Detect review candidates.
- Group project-related files deterministically.
- Suggest organization plans.
- Optionally refine organization suggestions with local Ollama.
- Apply approved organization plans with undo logs.
- Undo logged move operations.

Stage 8.5 is a stabilization and documentation pass. Stage 9 scheduled reporting, GUI work, cloud APIs, and prompt evaluation tooling are not implemented.

## Setup

Use Python 3 and the standard library. No third-party dependencies are required for the current test suite.

```bash
PYTHONPATH=src python3 -m unittest tests.test_scanner tests.test_safety tests.test_duplicates tests.test_planner tests.test_executor tests.test_review tests.test_grouping tests.test_llm_refinement tests.test_organization_apply
```

## Quickstart

Run commands with `PYTHONPATH=src` from the repository root:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --duplicates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-organization
```

Apply commands require exact confirmation:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Undo uses an operation log path printed by an apply command:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --undo-log /path/to/folder/AI_Review/operation_logs/operation_log_YYYYMMDD.json
```

## CLI Examples

Read-only and dry-run commands:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --max-depth 2
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --review-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --project-groups
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-review-candidates
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-duplicates
```

Approved move commands:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-duplicate-plan --confirm APPLY_DUPLICATE_PLAN
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-organization-plan --confirm APPLY_ORGANIZATION_PLAN
```

Local Ollama refinement:

```bash
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --refine-groups --llm-provider ollama --llm-model qwen2.5:7b
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --plan-refined-organization --llm-provider ollama --llm-model qwen2.5:7b
PYTHONPATH=src python3 -m organizer.cli /path/to/folder --apply-refined-organization-plan --llm-provider ollama --llm-model qwen2.5:7b --confirm APPLY_REFINED_ORGANIZATION_PLAN
```

## Safety Notes

- Use a small disposable folder for manual testing.
- Inspect dry-run output before using exact confirmation.
- Keep operation logs when testing undo.
- Do not run apply commands on important folders while testing.
- `executor.py` is the only module that performs real movement.
- Review, grouping, and LLM modules produce facts or suggestions; they do not execute moves.

## Documentation

- [Documentation index](docs/README.md)
- [CLI reference](docs/CLI_REFERENCE.md)
- [Manual testing guide](docs/MANUAL_TESTING.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Safety constitution](docs/SAFETY.md)
