# Local File Organizer Documentation

This project is a cautious local file organizer. It scans a chosen folder, reports metadata, detects exact duplicates, proposes dry-run review and organization plans, and can apply only approved duplicate moves with operation logs.

Deterministic Python is the source of truth for facts. LLM output is advisory only and stored separately as `LLMRefinement`. `executor.py` is the only module allowed to move files.

## Current Status

Stages 1 through 7 are implemented. Stage 7.5 adds this documentation and prompt framework. Organization plans and refined organization plans are still dry-run only.

## Quick Navigation

- [ROADMAP](ROADMAP.md)
- [ARCHITECTURE](ARCHITECTURE.md)
- [SAFETY](SAFETY.md)
- [CLI_REFERENCE](CLI_REFERENCE.md)
- [DESIGN_DECISIONS](DESIGN_DECISIONS.md)
- [DEVELOPMENT_GUIDE](DEVELOPMENT_GUIDE.md)
- [CODEX_INSTRUCTIONS](CODEX_INSTRUCTIONS.md)
- [Prompt Framework](prompts/README.md)
- [Research Notes](research/README.md)

## Safety Philosophy

The system separates facts, suggestions, and execution. Scanners and detectors collect facts. Planners build suggested dry-run actions. Execution requires explicit approval and writes an operation log. No module should remove files permanently.
