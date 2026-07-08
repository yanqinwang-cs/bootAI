# Prompt Framework

Prompts are engineering artifacts. They define model inputs, allowed outputs, validation rules, and failure expectations.

## Structure

- `group_refinement.md`: current Stage 7 group refinement prompt.
- `prompt_guidelines.md`: reusable prompt rules.
- `prompt_versions.md`: prompt version history.
- `evaluation.md`: future evaluation metrics.
- `schemas/`: documentation-only schema references.
- `examples/`: representative prompt payloads and expected responses.

## Design Goals

- Compact metadata.
- Structured JSON-only responses.
- Provider-agnostic prompt shape where possible.
- Python-side validation.
- No filesystem actions.
- No full file contents by default.
