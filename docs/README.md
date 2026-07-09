# Local File Organizer Documentation

This project is a cautious local file organizer. It scans a chosen folder, reports metadata, detects exact duplicates, proposes dry-run review and organization plans, writes read-only JSON and HTML reports, and can apply approved duplicate and organization moves with operation logs.

Deterministic Python is the source of truth for facts. LLM output is advisory only and stored separately as `LLMRefinement`. `executor.py` is the only module allowed to move files.

## Current Status

Stages 1 through 10.4.4 are implemented. Stage 10.4 adds a static HTML report viewer generated from the JSON report data. Stage 10.4.1 makes normal organization conservative by default. Stage 10.4.2 excludes protected contexts from actionable move plans. Stage 10.4.3 requires strong organization anchors, suppresses weak token groups, assigns role-based subfolders after grouping, and excludes generated web/archive assets from actionable plans. Stage 10.4.4 adds optional read-only organization rules and alias-normalized anchor-decision reporting. Built-in scheduler daemons, broad code organization, saved review-session resume/editing, filtering/sorting/pagination, HTML review actions, and GUI work remain future work.

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

The system separates facts, suggestions, reviewed decisions, approved moves, execution, and undo. Scanners and detectors collect facts. Planners build suggested dry-run actions. Review state remembers human decisions only. Execution requires explicit approval and writes an operation log. Never permanently delete files.
