# Local File Organizer Documentation

This project is a cautious local file organizer. It scans a chosen folder, reports metadata, detects exact duplicates, proposes dry-run review and organization plans, writes read-only JSON and HTML reports, and can apply approved duplicate and organization moves with operation logs.

Deterministic Python is the source of truth for facts. LLM output is advisory only and stored separately as `LLMRefinement`. `executor.py` is the only module allowed to move files.

## Current Status

Stages 1 through 10.14 and Stages 11.0 through 11.5.2 are implemented. Guided Duplicates, Organize, and Needs attention queues now save independently while Advanced review retains the complete-session workflow.

Fresh web sessions normalize new/stale suggestions to `undecided` and preserve remembered decisions. Module artifacts reuse the reviewed-plan schema, include every underlying module row, and never move files. Queue progress and skipped state are generation-bound memory only. There is no scheduling, tree, autosave, web apply, or restore.

## Quick Navigation

- [ROADMAP](ROADMAP.md)
- [ARCHITECTURE](ARCHITECTURE.md)
- [WEB_ARCHITECTURE](WEB_ARCHITECTURE.md)
- [WEB_THREAT_MODEL](WEB_THREAT_MODEL.md)
- [SAFETY](SAFETY.md)
- [CLI_REFERENCE](CLI_REFERENCE.md)
- [REPORT_FORMAT](REPORT_FORMAT.md)
- [MANUAL_TESTING](MANUAL_TESTING.md)
- [RELEASE_NOTES](RELEASE_NOTES.md)
- [DESIGN_DECISIONS](DESIGN_DECISIONS.md)
- [DEVELOPMENT_GUIDE](DEVELOPMENT_GUIDE.md)
- [CODEX_INSTRUCTIONS](CODEX_INSTRUCTIONS.md)
- [ADR 0001: Local Web Stack](adr/0001-local-web-stack.md)
- [ADR 0002: Local Web Security Boundary](adr/0002-web-security-boundary.md)
- [ADR 0003: Application-Service Layer](adr/0003-application-service-layer.md)
- [Sample Report](examples/sample_report.json)
- [Sample Rule Candidates](examples/sample_rule_candidates.json)
- [Sample Rule Decisions](examples/sample_rule_decisions.json)
- [Sample Organization Review](examples/sample_organization_review.json)
- [Sample Organization Review Apply Result](examples/sample_organization_review_apply_result.json)
- [Sample Organization Apply Verification](examples/sample_organization_review_apply_verification.json)
- [Prompt Framework](prompts/README.md)
- [Research Notes](research/README.md)

## Safety Philosophy

The system separates facts, suggestions, reviewed decisions, approved moves, execution, and undo. Scanners and detectors collect facts. Planners build suggested dry-run actions. Review state remembers human decisions only. Execution requires explicit approval and writes an operation log. Never permanently delete files.
