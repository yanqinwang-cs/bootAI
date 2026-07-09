# Local File Organizer Documentation

This project is a cautious local file organizer. It scans a chosen folder, reports metadata, detects exact duplicates, proposes dry-run review and organization plans, writes read-only JSON and HTML reports, and can apply approved duplicate and organization moves with operation logs.

Deterministic Python is the source of truth for facts. LLM output is advisory only and stored separately as `LLMRefinement`. `executor.py` is the only module allowed to move files.

## Current Status

Stages 1 through 10.4 are implemented. Stage 10.4 adds a static HTML report viewer generated from the JSON report data. Built-in scheduler daemons, saved review-session resume/editing, filtering/sorting/pagination, HTML review actions, and GUI work remain future work.

## Quick Navigation

- [ROADMAP](ROADMAP.md)
- [ARCHITECTURE](ARCHITECTURE.md)
- [SAFETY](SAFETY.md)
- [CLI_REFERENCE](CLI_REFERENCE.md)
- [REPORT_FORMAT](REPORT_FORMAT.md)
- [MANUAL_TESTING](MANUAL_TESTING.md)
- [RELEASE_NOTES](RELEASE_NOTES.md)
- [DESIGN_DECISIONS](DESIGN_DECISIONS.md)
- [DEVELOPMENT_GUIDE](DEVELOPMENT_GUIDE.md)
- [CODEX_INSTRUCTIONS](CODEX_INSTRUCTIONS.md)
- [Sample Report](examples/sample_report.json)
- [Prompt Framework](prompts/README.md)
- [Research Notes](research/README.md)

## Safety Philosophy

The system separates facts, suggestions, reviewed decisions, approved moves, execution, and undo. Scanners and detectors collect facts. Planners build suggested dry-run actions. Review state remembers human decisions only. Execution requires explicit approval and writes an operation log. No module should permanently delete files.
