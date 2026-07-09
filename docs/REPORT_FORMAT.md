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
| `organization_rules` | Read-only organization-rules status and resolved rule metadata. | object |
| `rule_audit` | Read-only audit of how loaded organization rules affect report output. | object |
| `anchor_decisions` | Alias-normalized anchor decisions used for grouping reports. | object |
| `organization_pattern_inference` | Report-only inferred foldering patterns and manual rule candidates. | object |
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
- `suggested_anchor_count`: number of final suggested organization anchors.
- `needs_decision_anchor_count`: number of anchors reported for manual decision.
- `ignored_anchor_count`: number of final ignored anchors.
- `organization_pattern_count`: number of inferred foldering patterns.
- `inferred_rule_candidate_count`: number of report-only rule candidates.
- `refinement_status`: `not_requested`, `completed`, or `failed`.

## Organization Rules And Anchor Decisions

`organization_rules` reports whether `AI_Review/config/organization_rules.json`
was loaded or whether conservative built-in defaults were used. The file is
read-only in Stage 10.4.4; the CLI does not create, edit, or initialize it.

Supported rule concepts are:

- `locked_anchors`: anchors that can become suggested groups when at least two
  eligible safe files match.
- `ignored_terms`: anchors that should not create organization suggestions.
- `anchor_aliases`: alias-to-canonical mappings resolved before reporting.

Ignored terms win over locked anchors after alias normalization. Locked anchors
do not bypass protected/generated/project-output exclusions.

`anchor_decisions` has three user-facing sections:

- `suggested_groups`: narrow repeated document sets that can produce
  organization suggestions.
- `needs_decision`: broader anchors that are reported but do not produce
  `MovePlanItem` values unless later rules lock them or narrower evidence is
  detected.
- `ignored_terms`: anchors ignored by rules or conservative defaults.

Needs-decision entries may include `pattern_evidence` when existing folders
suggest that the anchor matches a local organization habit. This evidence is
report-only and contains:

- `priority`: `high`, `medium`, `low`, or `none`.
- `matched_patterns`: pattern types that matched.
- `reason`: a short explanation of the inferred local preference evidence.

## Existing Organization Pattern Inference

`organization_pattern_inference` contains weak local preference evidence from
existing folders. It is included automatically in JSON and HTML reports.

The section has:

- `patterns`: detected organization habits such as `course_code_foldering`,
  `project_foldering`, `person_or_student_foldering`, `role_foldering`,
  `year_foldering`, or `format_foldering`.
- `rule_candidates`: manual rule candidates such as
  `preferred_granularity_candidate` or `lock_anchor_candidate`.
  Each candidate includes `candidate_id`, `rule_type`, `value`, `confidence`,
  `reason`, `evidence_paths`, and `suggested_action`.

Folder evidence can come from exact folder names such as `CS1010X/` or compound
folders such as `cs1010x finals/`, `CS1010x PE/`, `EvoSim images/`, or
`ourdream/` when the folder contains eligible document-like files. This evidence
can enrich `Needs decision` anchors but does not make broad anchors actionable.

Pattern inference ignores tool-owned, protected, dependency, generated, and
project-output contexts. It does not write `organization_rules.json`, create
`MovePlanItem` values directly, approve moves, or change apply behavior.

Rule candidates are advisory. Exporting them for review writes a separate JSON
file under `AI_Review/rules/`; applying accepted decisions requires exact
`APPLY ORGANIZATION RULES` confirmation and updates configuration only.

## Rule-Aware Organization Audit

`rule_audit` is included automatically in JSON and HTML reports.

When no valid rules file is loaded, `rules_loaded` is `false`, rule effects are
empty, and warnings explain that the audit was skipped. Report generation does
not create, repair, or modify `organization_rules.json`.

When rules are loaded, the audit compares conservative built-in defaults against
the loaded rule-aware output in memory. It reports:

- `before_after_counts`: deterministic counts for needs-decision anchors,
  suggested anchors, ignored anchors, and organization suggestion counts.
- `rule_effects`: per-rule effects for locked anchors, ignored terms, aliases,
  and advisory preferred granularities.
- `warnings`: cautious report-only warnings for broad locked anchors or large
  suggestion-count increases.

Risk thresholds are deterministic: 0 to 10 matched files is `low`, 11 to 50 is
`medium`, and 51 or more is `high`. Preferred granularities remain advisory and
do not change organization behavior in Stage 10.7.

## Fact Sections

`duplicates`, `review_candidates`, and `project_groups` describe detected facts or
deterministic suggestions. They do not authorize movement.

Duplicate groups contain factual exact duplicate matches:

- `sha256`
- `size_bytes`
- `files`

Protected-context files may appear in `duplicates` because this section is
factual. Protected-context files are excluded from actionable plan sections by
default.

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

Actionable plan sections are stricter than factual sections. They exclude
protected contexts such as dependency folders, Git internals, virtual
environments, app/framework bundles, protected workspaces, and project/package
contexts by default. They also exclude generated web/archive assets and
contextual project-output folders such as browser-saved `*_files/` assets.

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

Reports also warn when protected-context exact duplicate facts are omitted from
the actionable duplicate review plan. The same warning class covers generated
and project-output contexts.

Warnings do not approve movement and do not change apply-command requirements.
