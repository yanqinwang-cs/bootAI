# Prompt Evaluation

Prompt quality should be measured before prompts are expanded.

## Hard Metrics

- JSON validity rate.
- Schema validity rate.
- Hallucinated path count.
- Omitted path count.
- Invalid subfolder count.
- Forbidden phrase count.
- Validation failure rate.

## Runtime Metrics

- Average latency.
- Average prompt size.
- Average output size.
- Local resource use.

## Regression Examples

Keep representative inputs and expected outputs in `examples/`. Future harnesses can compare outputs against schema validity, path preservation, allowed-value compliance, and forbidden phrase checks.

## Golden Examples

Golden examples should be small, stable fixtures that represent expected model behavior for common group types. They should include course-code groups, project-token groups, and messy download groups. They are documentation fixtures until a future stage explicitly adds an evaluator.

## Future Harness

A later documentation or evaluation stage can add a script that runs prompts against configured local models and reports metrics. Stage 7.6 does not add tooling.
