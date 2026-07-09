from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from organizer.reports import default_report_path, validate_report_output_path


def render_html_report(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>bootAI Report</title>",
            "  <style>",
            _stylesheet(),
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <h1>bootAI Report</h1>",
            "    <p class=\"lede\">Read-only report. Suggested moves are dry-run plan items and are not approved or applied by this HTML file.</p>",
            _metadata_section(report),
            _summary_section(report.get("summary")),
            _organization_rules_section(report.get("organization_rules")),
            _anchor_decisions_section(report.get("anchor_decisions")),
            _organization_pattern_inference_section(
                report.get("organization_pattern_inference")
            ),
            _warnings_section(report.get("warnings")),
            _plan_section(
                "Duplicate review plan",
                "dry-run plan item",
                report.get("duplicate_review_plan"),
            ),
            _review_candidates_section(report.get("review_candidates")),
            _plan_section(
                "Review candidate plan",
                "dry-run plan item",
                report.get("review_candidate_plan"),
            ),
            _project_groups_section(report.get("project_groups")),
            _organization_suggestions_section(
                "Organization suggestions",
                report.get("organization_suggestions"),
            ),
            _organization_suggestions_section(
                "Refined organization suggestions",
                report.get("refined_organization_suggestions"),
            ),
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def write_html_report(
    report: dict[str, object],
    root: Path,
    json_report_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    resolved_destination = html_report_output_path(root, json_report_path, output_path)
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved_destination.open("x", encoding="utf-8") as file:
        file.write(render_html_report(report))
    return resolved_destination


def html_report_output_path(
    root: Path,
    json_report_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    resolved_root = root.resolve()
    if output_path is None:
        if json_report_path is None:
            destination = default_report_path(resolved_root).with_suffix(".html")
        else:
            destination = json_report_path.with_suffix(".html")
    elif output_path.is_absolute():
        destination = output_path
    else:
        destination = resolved_root / output_path
    return validate_report_output_path(destination, resolved_root)


def _metadata_section(report: dict[str, object]) -> str:
    rows = [
        ("schema_version", report.get("schema_version", "")),
        ("generated_at", report.get("generated_at", "")),
        ("scan_root", report.get("scan_root", "")),
    ]
    return _section(
        "Metadata",
        _table(["Field", "Value"], [[key, value] for key, value in rows]),
    )


def _summary_section(summary: object) -> str:
    if not isinstance(summary, dict) or not summary:
        return _section("Summary", _empty_message())
    rows = [
        [key, _format_value(summary[key])]
        for key in sorted(summary)
    ]
    return _section("Summary", _table(["Metric", "Value"], rows))


def _warnings_section(warnings: object) -> str:
    if not isinstance(warnings, list) or not warnings:
        return _section("Warnings", _empty_message())
    items = "".join(f"<li>{_escape(warning)}</li>" for warning in warnings)
    return _section("Warnings", f"<ul class=\"warnings\">{items}</ul>")


def _organization_rules_section(rules: object) -> str:
    if not isinstance(rules, dict) or not rules:
        return _section("Organization rules", _empty_message())
    locked_anchors = rules.get("locked_anchors", [])
    locked_text = ", ".join(str(anchor) for anchor in locked_anchors) if isinstance(locked_anchors, list) and locked_anchors else "None"
    rows = [
        ["Status", rules.get("status", "")],
        ["Path", rules.get("path", "") or "(built-in defaults)"],
        ["Message", rules.get("message", "")],
        ["Locked anchors", locked_text],
    ]
    return _section("Organization rules", _table(["Field", "Value"], rows))


def _anchor_decisions_section(anchor_decisions: object) -> str:
    if not isinstance(anchor_decisions, dict) or not anchor_decisions:
        return _section("Anchor decisions", _empty_message())
    blocks = [
        (
            "<p>Suggested groups are narrow file sets bootAI is willing to organize "
            "in dry-run mode. Needs decision contains broader patterns that may "
            "depend on your personal organization preference.</p>"
        ),
        _anchor_decision_table("Suggested groups", anchor_decisions.get("suggested_groups")),
        _anchor_decision_table("Needs decision", anchor_decisions.get("needs_decision")),
        _anchor_decision_table("Ignored terms", anchor_decisions.get("ignored_terms")),
    ]
    return _section("Anchor decisions", "".join(blocks))


def _anchor_decision_table(title: str, decisions: object) -> str:
    if not isinstance(decisions, list) or not decisions:
        return f"<h3>{_escape(title)}</h3>{_empty_message()}"
    rows = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        examples = decision.get("examples", [])
        rows.append(
            [
                decision.get("anchor", ""),
                decision.get("file_count", ""),
                decision.get("evidence", ""),
                _pattern_evidence_summary(decision.get("pattern_evidence")),
                decision.get("reason", ""),
                ", ".join(str(example) for example in examples) if isinstance(examples, list) else "",
            ]
        )
    if not rows:
        return f"<h3>{_escape(title)}</h3>{_empty_message()}"
    return (
        f"<h3>{_escape(title)}</h3>"
        + _table(["Anchor", "Files", "Evidence", "Pattern evidence", "Reason", "Examples"], rows)
    )


def _organization_pattern_inference_section(inference: object) -> str:
    if not isinstance(inference, dict) or not inference:
        return _section("Inferred organization patterns", _empty_message())
    patterns = inference.get("patterns")
    rule_candidates = inference.get("rule_candidates")
    blocks = [
        (
            "<p>bootAI found existing folder patterns that may reflect how this "
            "root is already organized. These are suggestions only. They do not "
            "change rules or move files automatically.</p>"
        ),
        _pattern_table(patterns),
        _rule_candidate_table(rule_candidates),
    ]
    return _section("Inferred organization patterns", "".join(blocks))


def _pattern_table(patterns: object) -> str:
    if not isinstance(patterns, list) or not patterns:
        return "<h3>Patterns</h3>" + _empty_message()
    rows = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        rows.append(
            [
                pattern.get("pattern_type", ""),
                pattern.get("confidence", ""),
                pattern.get("reason", ""),
                pattern.get("examples", []),
                pattern.get("affected_anchors", []),
            ]
        )
    if not rows:
        return "<h3>Patterns</h3>" + _empty_message()
    return (
        "<h3>Patterns</h3>"
        + _table(
            ["Pattern type", "Confidence", "Reason", "Examples", "Affected anchors"],
            rows,
        )
    )


def _rule_candidate_table(rule_candidates: object) -> str:
    if not isinstance(rule_candidates, list) or not rule_candidates:
        return "<h3>Suggested rule candidates</h3>" + _empty_message()
    rows = []
    for candidate in rule_candidates:
        if not isinstance(candidate, dict):
            continue
        rows.append(
            [
                candidate.get("candidate_id", ""),
                candidate.get("rule_type", ""),
                candidate.get("value", ""),
                candidate.get("confidence", ""),
                candidate.get("reason", ""),
                candidate.get("evidence_paths", []),
                candidate.get("suggested_action", ""),
            ]
        )
    if not rows:
        return "<h3>Suggested rule candidates</h3>" + _empty_message()
    return (
        "<h3>Suggested rule candidates</h3>"
        + _table(
            [
                "Candidate ID",
                "Rule type",
                "Value",
                "Confidence",
                "Reason",
                "Evidence paths",
                "Suggested action",
            ],
            rows,
        )
    )


def _pattern_evidence_summary(pattern_evidence: object) -> str:
    if not isinstance(pattern_evidence, dict):
        return ""
    priority = pattern_evidence.get("priority", "")
    reason = pattern_evidence.get("reason", "")
    matched = pattern_evidence.get("matched_patterns", [])
    matched_text = ", ".join(str(pattern) for pattern in matched) if isinstance(matched, list) else str(matched)
    return f"{priority}: {matched_text}. {reason}".strip()


def _review_candidates_section(candidates: object) -> str:
    if not isinstance(candidates, list) or not candidates:
        return _section("Review candidates", _empty_message())
    rows = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        rows.append(
            [
                candidate.get("path", ""),
                candidate.get("category", ""),
                candidate.get("reason", ""),
                candidate.get("confidence", ""),
            ]
        )
    if not rows:
        return _section("Review candidates", _empty_message())
    return _section(
        "Review candidates",
        "<p>Candidate for review entries are informational only.</p>"
        + _table(["Path", "Category", "Reason", "Confidence"], rows),
    )


def _plan_section(title: str, label: str, plan_items: object) -> str:
    if not isinstance(plan_items, list) or not plan_items:
        return _section(title, _empty_message())
    rows = []
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                label,
                item.get("source", ""),
                item.get("destination", ""),
                item.get("reason", ""),
                item.get("confidence", ""),
                item.get("overwrite_risk", ""),
            ]
        )
    if not rows:
        return _section(title, _empty_message())
    return _section(
        title,
        _table(
            ["Type", "Source", "Destination", "Reason", "Confidence", "Overwrite risk"],
            rows,
        ),
    )


def _project_groups_section(groups: object) -> str:
    if not isinstance(groups, list) or not groups:
        return _section("Project groups", _empty_message())
    rows = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        files = group.get("files", [])
        file_count = len(files) if isinstance(files, list) else 0
        rows.append(
            [
                group.get("group_name", ""),
                group.get("reason", ""),
                group.get("confidence", ""),
                file_count,
            ]
        )
    if not rows:
        return _section("Project groups", _empty_message())
    return _section(
        "Project groups",
        _table(["Suggested group", "Reason", "Confidence", "File count"], rows),
    )


def _organization_suggestions_section(title: str, suggestions: object) -> str:
    if not isinstance(suggestions, list) or not suggestions:
        return _section(title, _empty_message())

    blocks: list[str] = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        group_name = _escape(suggestion.get("group_name", ""))
        suggested_root = _escape(suggestion.get("suggested_root", ""))
        plan_items = suggestion.get("plan_items", [])
        blocks.append(
            "<article class=\"suggestion\">"
            f"<h3>{group_name}</h3>"
            f"<p><strong>Suggested root:</strong> {suggested_root}</p>"
            + _plan_section_body(plan_items)
            + "</article>"
        )
    if not blocks:
        return _section(title, _empty_message())
    return _section(title, "".join(blocks))


def _plan_section_body(plan_items: object) -> str:
    if not isinstance(plan_items, list) or not plan_items:
        return _empty_message()
    rows = []
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                "suggested move",
                item.get("source", ""),
                item.get("destination", ""),
                item.get("reason", ""),
                item.get("confidence", ""),
                item.get("overwrite_risk", ""),
            ]
        )
    if not rows:
        return _empty_message()
    return _table(
        ["Type", "Source", "Destination", "Reason", "Confidence", "Overwrite risk"],
        rows,
    )


def _section(title: str, body: str) -> str:
    return f"<section><h2>{_escape(title)}</h2>{body}</section>"


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{_escape(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_escape(_format_value(value))}</td>" for value in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        "<table>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def _empty_message() -> str:
    return '<p class="empty">No entries in this section.</p>'


def _format_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}: {value[key]}" for key in sorted(value))
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _stylesheet() -> str:
    return """
    :root {
      color-scheme: light;
      --border: #c9d3df;
      --text: #17202a;
      --muted: #526170;
      --panel: #f7f9fb;
      --warning: #8a5a00;
      --warning-bg: #fff7d6;
    }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: #ffffff;
      line-height: 1.45;
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }
    h1, h2, h3 {
      margin: 0 0 12px;
    }
    h1 {
      font-size: 30px;
    }
    h2 {
      font-size: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }
    h3 {
      font-size: 16px;
    }
    .lede, .empty {
      color: var(--muted);
    }
    section {
      margin-top: 28px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-top: 10px;
      background: #ffffff;
    }
    th, td {
      border: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      background: var(--panel);
    }
    .warnings {
      border: 1px solid #e6c878;
      background: var(--warning-bg);
      color: var(--warning);
      padding: 12px 12px 12px 30px;
    }
    .suggestion {
      border: 1px solid var(--border);
      padding: 14px;
      margin-top: 12px;
      background: #ffffff;
    }
    """
