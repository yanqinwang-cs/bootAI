# Safety Constitution

## Invariants

- Never permanently delete files.
- Never overwrite files.
- Never move outside the selected scan root.
- Always validate paths against the selected scan root.
- Dry-run is the default behavior.
- Exact explicit confirmation is required for apply behavior.
- Every successful move requires an operation log.
- Undo support is required for real movement.
- Direct symlink sources are rejected for moving.
- Unsafe symlink destination parents are rejected.
- Deterministic Python is the source of truth for facts.
- LLM output is advisory only.
- Full file contents are not sent to the LLM by default.
- Planner, review, grouping, and LLM modules must not move files.
- `executor.py` is the only movement module.

## Risk Categories

- Exact duplicates: files with matching SHA-256 hashes.
- Empty files: candidate for review unless they are known placeholders.
- Temporary files: candidate for review when filename patterns match system or temporary artifacts.
- Backup or copy files: candidate for review when filename tokens indicate version markers.
- Project organization candidates: suggested groups based on deterministic course-code or token signals.

## Language Rules

Use cautious language: `candidate for review`, `suggested`, `dry-run`, `approved move`, and `operation log`. Avoid claims that imply disposal, automatic action, or certainty beyond the deterministic facts.

Do not use these phrases except when listing forbidden wording:

- `safe to delete`
- `useless`
- `automatic cleanup`
- `permanent cleanup`
