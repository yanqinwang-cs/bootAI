# Token Optimization

## Principles

- Send relative paths only.
- Send metadata, not content.
- Omit redundant prose.
- Use allowed-value lists.
- Keep examples outside runtime prompts unless an evaluated future prompt version needs them.

## Prompt Bloat Risks

Long prompts can increase latency and make local models less consistent. Runtime prompts should stay close to the compact Stage 7 shape.

## Future Metrics

- Prompt size.
- Output size.
- Validation pass rate.
- Average latency.
- Model-specific context pressure.
