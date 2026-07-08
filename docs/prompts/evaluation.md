# Prompt Evaluation

Prompt quality should be measured before prompts are expanded.

## Hard Metrics

- JSON validity rate.
- Schema validity rate.
- Hallucinated path count.
- Omitted path count.
- Invalid subfolder count.
- Blocked phrase count.
- Validation failure rate.

## Runtime Metrics

- Average latency.
- Average prompt size.
- Average output size.
- Local resource use.

## Regression Examples

Keep representative inputs and expected outputs in `examples/`. Future harnesses can compare outputs against schema validity, path preservation, and allowed-value compliance.

## Future Harness

A later documentation or evaluation stage can add a script that runs prompts against configured local models and reports metrics. Stage 7.5 does not add tooling.
