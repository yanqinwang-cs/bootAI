# Report Format

Stage 9 reports are JSON files written by `python -m organizer.cli <folder> --report`.
They are intended for manual review or external scheduler runs. A report contains
facts and dry-run suggestions only.

Reports do not approve moves. Reports do not move files. Apply commands remain
separate and require exact confirmation.

Stage 10.4 adds `--html-report`, which writes the same JSON report plus a static
HTML rendering of that report dictionary. The JSON report remains the
machine-readable source of truth. The HTML report is a browser-openable viewer
only: it does not approve moves, apply moves, perform review actions, write
operation logs, or start a server.

## Path Rules

- Paths inside report sections are relative to the selected scan root.
- `scan_root` is currently `"."` to avoid storing absolute local paths.
- Report output paths are validated under the scan root.
- HTML report output paths are validated under the scan root and are refused if
  they already exist.
- Reports do not contain full file contents or previews.

## Top-Level Fields

| Field | Meaning | Type |
| --- | --- | --- |
| `schema_version` | Report schema version. Current value is `1`. | integer |
| `generated_at` | UTC ISO timestamp for report generation. | string |
| `scan_root` | Relative marker for the scanned root. Current value is `"."`. | string |
| `summary` | Compact counts and refinement status. | object |
| `duplicates` | Exact duplicate facts from SHA-256 grouping. | array |
| `duplicate_review_plan` | Dry-run suggestions for duplicate review moves. | array |
| `review_candidates` | Heuristic review candidates. | array |
| `review_candidate_plan` | Dry-run suggestions for review candidate moves. | array |
| `project_groups` | Deterministic suggested project groups. | array |
| `organization_suggestions` | Dry-run deterministic organization suggestions. | array |
| `refined_organization_suggestions` | Dry-run local-LLM refined suggestions, if requested and valid. | array |
| `warnings` | Non-fatal report-generation warnings. | array |

## `summary`

`summary` is factual metadata about the report contents:

- `file_count`: number of scanned non-directory items.
- `total_bytes`: total size of scanned non-directory items.
- `duplicate_group_count`: number of exact duplicate groups.
- `duplicate_candidate_count`: number of duplicate review plan items.
- `review_candidate_count`: number of heuristic review candidates.
- `review_candidate_counts_by_category`: candidate counts by category.
- `project_group_count`: number of deterministic project groups.
- `organization_suggestion_count`: total deterministic organization plan items.
- `refinement_status`: `not_requested`, `completed`, or `failed`.

## Fact Sections

`duplicates`, `review_candidates`, and `project_groups` describe detected facts or
deterministic suggestions. They do not authorize movement.

Duplicate groups contain:

- `sha256`
- `size_bytes`
- `files`

Review candidates contain:

- `path`
- `category`
- `reason`
- `confidence`

Current review candidate categories include `temporary`, `empty`, `backup_or_copy`,
and `orphan_code`. `orphan_code` means an isolated code file outside detected
project/package/application contexts; it is still only a candidate for review.

Project groups contain:

- `group_name`
- `reason`
- `confidence`
- `files`

## Dry-Run Suggestion Sections

`duplicate_review_plan`, `review_candidate_plan`, `organization_suggestions`,
and `refined_organization_suggestions` contain dry-run `MovePlanItem` data. These
sections can inform later review, but they do not apply moves.

Plan items contain:

- `source`
- `destination`
- `reason`
- `confidence`
- `operation`
- `overwrite_risk`

`operation` is expected to be `dry-run move` for current planning output.

Organization suggestions contain:

- `group_name`
- `suggested_root`
- `plan_items`

Refined organization suggestions have the same report shape as deterministic
organization suggestions. Refinement is advisory only; deterministic Python
remains the source of truth for facts.

## Warnings

`warnings` is a list of strings. For example, invalid local LLM refinement output
can produce a warning and leave `refined_organization_suggestions` empty.

Reports also warn when deterministic organization suggestions are unusually
broad, either above 1000 suggested moves or above half of the scanned file count.
This warning is a review guardrail only and does not change apply requirements.

Warnings do not approve movement and do not change apply-command requirements.
