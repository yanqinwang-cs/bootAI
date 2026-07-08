# Hallucination Risks

## Risks

- Invented file paths.
- Omitted files.
- Invalid subfolders.
- Overconfident reasons.
- Action language that implies execution.
- Cleanup or removal language.

## Mitigations

- Compact payloads.
- Strict JSON.
- Python validation.
- Blocked phrase checks.
- Exact path matching.
- Allowed-value subfolders.

Invalid model output is rejected rather than repaired silently.
