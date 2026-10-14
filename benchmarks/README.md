# Synthetic benchmark

Run from the repository root:

```bash
python benchmarks/run.py
```

`cases.json` contains four fictional scenarios (software development, writing, product design, and data analysis). Each case includes a feedback event, expected structured scope and exclusion, one applicable and one excluded task, and three outputs with expected violation labels. No external model calls are made.

## Metrics

- **Rule extraction accuracy** = feedback events whose parsed origin, directive, applicable scope, negative boundaries, and configured deterministic checks all equal the fixture expectation ÷ feedback events.
- **Scope accuracy** = correct positive-scope activation plus correct negative-boundary exclusion ÷ all scope decisions.
- **Error-generalization rate** = negative-scope tasks where the rule still activates ÷ negative-scope tasks.
- **Violation precision** = TP ÷ (TP + FP); **recall** = TP ÷ (TP + FN); **accuracy** = (TP + TN) ÷ output checks. A predicted violation means the engine returns `violations_found` for the fixture's configured exact phrase.

The runner prints each numerator, denominator, and rate. The current fixture has 4 feedback events, 8 scope decisions, and 12 output checks. Results only test these synthetic paths; they do not estimate general language accuracy, user outcomes, or model performance.

Current deterministic run: extraction `4/4`, scope `8/8`, false activations `0/4`, and output checks `TP=4, FP=0, FN=0, TN=8` (precision `4/4`, recall `4/4`). This is the expected behavior on the authored fixtures, not a claim about unseen data.
