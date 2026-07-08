# Prompt Guidelines

## Rules

- Use one task per prompt.
- Use deterministic preprocessing before prompting.
- Send metadata before content.
- Do not send full contents by default.
- Request JSON only.
- Define allowed values.
- Require exact input path preservation.
- Keep prompts compact.
- Validate output outside the model.
- Reject invalid output.
- Do not ask the model to decide filesystem facts.

## Anti-Patterns

- Broad open-ended organization requests.
- Asking for file actions.
- Asking for subjective disposal judgments.
- Broad free-form summaries when structured output is needed.
- Letting the model invent paths, categories, or actions.
