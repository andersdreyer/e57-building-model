# Contributing

Please open an issue before beginning a substantial feature so the intended behaviour and source-of-truth rules can be discussed.

## Ground rules

- Keep scan data, plans, addresses, coordinates, screenshots, and client material out of commits and issues.
- Do not add a model feature that silently treats inferred geometry as a locked fact.
- Preserve the distinction between measurement evidence, user-provided constraints, and assumptions.
- Add or update tests for changes to numeric calculations or manifest validation.
- Run `python -m unittest discover -s tests -v` and the relevant syntax checks before opening a pull request.

## Pull requests

Describe the input, expected output, safety or uncertainty implications, and how you tested the change. Use synthetic data whenever a test needs point geometry.
