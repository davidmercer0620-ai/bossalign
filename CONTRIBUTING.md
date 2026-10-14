# Contributing to BossAlign

BossAlign aims to turn human feedback into scoped, traceable rules while avoiding accidental generalization. Contributions should keep the core domain-neutral and make uncertainty visible.

## Local setup

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check bossalign tests benchmarks
```

Python 3.9 is the minimum supported version. The runtime package should remain standard-library-only unless a concrete requirement justifies a dependency.

## Contribution guidelines

- Add tests for behavior and negative cases: nonmatching scope, missing context, unconfirmed proposals, conflicts, and reviewer isolation.
- Keep provider-specific behavior behind `FeedbackProvider`; do not put vendor calls in the parser, store, CLI, or boundary engine.
- Do not promote inferred proposals to confirmed rules in code.
- Keep rules, examples, and benchmark data synthetic. Do not submit real user feedback, API keys, private prompts, or confidential data.
- Avoid claims of semantic or production reliability that are not supported by tests and evidence.
- Update the English and Chinese user documentation when public behavior changes.

## Pull requests

1. Use a focused branch and describe the behavior change and its limits.
2. Include tests and a reproducible example where appropriate.
3. Run the local checks above.
4. Note any provider calls or compatibility assumptions; never include secrets in logs or fixtures.

The project uses MIT licensing. By contributing, you agree that your contribution is provided under that license.
