# Safety Constitution

## Invariants

- Never remove files permanently.
- Never overwrite files.
- Never move outside the selected scan root.
- Validate all execution paths against the root.
- Dry-run is the default behavior.
- Explicit confirmation is required for apply behavior.
- Operation logs are required for moves.
- Undo support is required for moves.
- Direct symlink sources are rejected for moves.
- Unsafe symlink parents are rejected for destination paths.
- LLM output is advisory only.
- Full file contents are not sent to the LLM by default.

## Risk Categories

- Exact duplicates: files with matching SHA-256 hashes.
- Empty files: candidate for review unless they are known placeholders.
- Temporary files: candidate for review when filename patterns match system or temporary artifacts.
- Backup or copy files: candidate for review when filename tokens indicate version markers.
- Project organization candidates: suggested groups based on deterministic course-code or token signals.

## Language Rules

Use cautious language: `candidate for review`, `suggested`, `dry-run`, `approved move`, and `operation log`. Avoid claims that imply disposal, automatic action, or certainty beyond the deterministic facts.
