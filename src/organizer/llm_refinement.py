import json
from pathlib import Path

from organizer.grouping import infer_subfolder
from organizer.models import LLMRefinement, MovePlanItem, OrganizationSuggestion, ProjectGroup

ALLOWED_SUBFOLDERS = {
    "papers",
    "notes",
    "code",
    "datasets",
    "results",
    "slides",
    "images",
    "archives",
    "documents",
    "other",
}

FORBIDDEN_OUTPUT_WORDS = {
    "delete",
    "safe to delete",
    "useless",
    "cleanup automatically",
    "permanent cleanup",
    "overwrite",
}


def build_group_refinement_payload(group: ProjectGroup) -> dict:
    return {
        "group_name": group.group_name,
        "reason": group.reason,
        "confidence": group.confidence,
        "files": [
            {
                "relative_path": file.relative_path.as_posix(),
                "name": file.name,
                "extension": file.extension,
                "deterministic_subfolder": infer_subfolder(file),
            }
            for file in sorted(group.files, key=lambda item: item.relative_path.as_posix())
        ],
    }


def build_group_refinement_messages(group: ProjectGroup) -> list[dict[str, str]]:
    payload = build_group_refinement_payload(group)
    schema = {
        "folder_name": "string",
        "confidence": 0,
        "reason": "string",
        "subfolders": {"relative/path/from/input.ext": "allowed_subfolder"},
        "warnings": [],
    }
    user_content = (
        "Return JSON only. No markdown. No prose outside JSON.\n"
        f"Schema: {json.dumps(schema, sort_keys=True)}\n"
        f"Allowed subfolders: {json.dumps(sorted(ALLOWED_SUBFOLDERS))}\n"
        "Rules: use every provided file path exactly once in subfolders; "
        "do not invent or omit paths; use only allowed subfolders; "
        "keep folder_name short and filesystem-friendly; if unsure, preserve "
        "the deterministic group name; confidence must be an integer 0-100.\n"
        f"Payload: {json.dumps(payload, sort_keys=True)}"
    )
    return [
        {
            "role": "system",
            "content": (
                "You refine deterministic file groups for a cautious local file "
                "organizer. Return only valid JSON. Do not suggest deletion, "
                "overwriting, automatic cleanup, or filesystem actions. Use only "
                "the provided file paths."
            ),
        },
        {"role": "user", "content": user_content},
    ]


def parse_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON response: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def validate_refinement_data(data: dict, group: ProjectGroup) -> LLMRefinement:
    folder_name = data.get("folder_name")
    confidence = data.get("confidence")
    reason = data.get("reason")
    subfolders = data.get("subfolders")
    warnings = data.get("warnings")

    if not isinstance(folder_name, str) or not folder_name.strip():
        raise ValueError("folder_name must be a non-empty string")
    if "/" in folder_name or "\\" in folder_name or folder_name in {".", ".."}:
        raise ValueError("folder_name must not contain path separators")
    if not isinstance(confidence, int) or confidence < 0 or confidence > 100:
        raise ValueError("confidence must be an integer from 0 to 100")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    if not isinstance(warnings, list) or not all(
        isinstance(warning, str) for warning in warnings
    ):
        raise ValueError("warnings must be a list of strings")
    if not isinstance(subfolders, dict):
        raise ValueError("subfolders must be an object")

    expected_paths = {
        file.relative_path.as_posix()
        for file in sorted(group.files, key=lambda item: item.relative_path.as_posix())
    }
    actual_paths = set(subfolders.keys())
    if actual_paths != expected_paths:
        raise ValueError("subfolders keys must exactly match group file paths")
    if any(value not in ALLOWED_SUBFOLDERS for value in subfolders.values()):
        raise ValueError("subfolder values must be allowed subfolders")

    _reject_forbidden_text([folder_name, reason, *warnings, *subfolders.values()])
    return LLMRefinement(
        original_group_name=group.group_name,
        folder_name=folder_name,
        confidence=confidence,
        reason=reason,
        subfolders=dict(subfolders),
        warnings=list(warnings),
    )


def refine_group_with_response(
    group: ProjectGroup,
    response_text: str,
) -> LLMRefinement:
    return validate_refinement_data(parse_json_object(response_text), group)


def build_refined_organization_suggestion(
    group: ProjectGroup,
    refinement: LLMRefinement,
    root: Path,
    organized_folder_name: str = "Organized",
) -> OrganizationSuggestion:
    safe_folder_name = _safe_group_name(refinement.folder_name)
    if safe_folder_name == "group":
        safe_folder_name = _safe_group_name(group.group_name)
    suggested_root = root / organized_folder_name / safe_folder_name
    plan_items: list[MovePlanItem] = []
    used_destinations: set[Path] = set()

    for file in sorted(group.files, key=lambda item: item.relative_path.as_posix()):
        relative_path = file.relative_path.as_posix()
        subfolder = refinement.subfolders[relative_path]
        destination = suggested_root / subfolder / file.name
        destination = _avoid_destination_collision(destination, file.relative_path, used_destinations)
        used_destinations.add(destination)
        plan_items.append(
            MovePlanItem(
                source=file.path,
                destination=destination,
                reason=f"LLM refinement: {refinement.reason}; suggested subfolder {subfolder}",
                confidence=refinement.confidence,
                operation="dry-run move",
                overwrite_risk=destination.exists(),
            )
        )

    return OrganizationSuggestion(
        group=group,
        suggested_root=suggested_root,
        plan_items=plan_items,
    )


def refine_project_groups_with_ollama(
    groups: list[ProjectGroup],
    client: object,
) -> list[LLMRefinement]:
    refinements: list[LLMRefinement] = []
    for group in groups:
        chat = getattr(client, "chat", None)
        if chat is None:
            raise RuntimeError("client must provide chat(messages)")
        response_text = chat(build_group_refinement_messages(group))
        refinements.append(refine_group_with_response(group, response_text))
    return refinements


def _reject_forbidden_text(values: list[str]) -> None:
    for value in values:
        lowered = value.lower()
        for phrase in FORBIDDEN_OUTPUT_WORDS:
            if phrase in lowered:
                raise ValueError(f"LLM output contains forbidden phrase: {phrase}")


def _safe_group_name(group_name: str) -> str:
    name = group_name.replace("/", "-").replace("\\", "-").strip().replace(" ", "_")
    sanitized = "".join(
        character
        for character in name
        if character.isalnum() or character in {"_", "-"}
    )
    return sanitized or "group"


def _avoid_destination_collision(
    destination: Path,
    relative_path: Path,
    used_destinations: set[Path],
) -> Path:
    if destination not in used_destinations:
        return destination
    prefixed_destination = destination.with_name(
        f"{_parent_prefix(relative_path)}_{destination.name}"
    )
    if prefixed_destination not in used_destinations:
        return prefixed_destination
    counter = 2
    while True:
        candidate = destination.with_name(
            f"{prefixed_destination.stem}_{counter}{destination.suffix}"
        )
        if candidate not in used_destinations:
            return candidate
        counter += 1


def _parent_prefix(relative_path: Path) -> str:
    parent = relative_path.parent.as_posix()
    if parent in {"", "."}:
        return "root"
    prefix = parent.replace("/", "_").replace("\\", "_")
    sanitized = "".join(
        character
        for character in prefix
        if character.isalnum() or character in {"_", "-"}
    )
    return sanitized or "root"
