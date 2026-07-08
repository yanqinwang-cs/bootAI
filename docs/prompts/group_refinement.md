# Group Refinement Prompt

## Purpose

The Stage 7 prompt asks a local Ollama model to refine deterministic `ProjectGroup` names and subfolder assignments. The model is advisory only. Python keeps the original `ProjectGroup` as the source of truth and stores model output separately as `LLMRefinement`.

## Input Payload

`build_group_refinement_payload()` sends:

- `group_name`
- `reason`
- `confidence`
- `files`

Each file item includes:

- `relative_path`
- `name`
- `extension`
- `deterministic_subfolder`

No absolute paths or file contents are sent.

## Current Message Shape

System message intent:

```text
Refine deterministic file groups for a cautious local file organizer. Return only valid JSON. Do not suggest removal, replacement, automated cleanup, or filesystem actions. Use only provided file paths.
```

User message includes:

- strict schema
- allowed subfolders
- exact path preservation rules
- payload JSON

## Required Output

```json
{
  "folder_name": "string",
  "confidence": 0,
  "reason": "string",
  "subfolders": {
    "relative/path/from/input.ext": "allowed_subfolder"
  },
  "warnings": []
}
```

Validation requires:

- top-level JSON object
- non-empty `folder_name` with no path separators and not `.` or `..`
- integer `confidence` from `0` to `100`
- non-empty `reason`
- `warnings` as a list of strings
- `subfolders` keys exactly matching all input relative paths
- `subfolders` values from the allowed list
- no blocked removal, replacement, or cleanup phrases in text fields

`parse_json_object()` accepts clean JSON, surrounding whitespace, and simple fenced JSON. The prompt still asks for JSON only.

## Allowed Subfolders

`papers`, `notes`, `code`, `datasets`, `results`, `slides`, `images`, `archives`, `documents`, `other`

## Failure Modes

Python rejects invalid JSON, invented paths, omitted paths, invalid subfolder values, invalid confidence, invalid folder names, and blocked text. It does not repair model output silently.

## Example

Input: see `examples/cs2103_input.json`.

Expected output: see `examples/cs2103_expected.json`.

## Token Notes

Keep runtime prompts compact. Examples live in documentation and should not be included in runtime prompts unless a future stage explicitly adds evaluated few-shot prompting.
