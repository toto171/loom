<!-- Thanks for contributing to Loom! Keep this concise. -->

## What & why

<!-- What does this change do, and why? Link any issue (Fixes #123). -->

## How it was tested

<!-- Commands you ran, scenarios exercised, new tests added. -->

## Scope deliberately left out

<!-- Anything you chose not to do, and why. Honest scoping is valued here. -->

## Checklist

- [ ] `ruff check .` is clean and `pytest` is green locally.
- [ ] New rules/features have a **passing and a failing** test (see [CONTRIBUTING](../CONTRIBUTING.md) §4).
- [ ] Docs updated if behavior, CLI, schema, or routes changed (`docs/`, `README.md`).
- [ ] Did **not** weaken the safety/security invariants (gate, lock, predicate sandbox,
      input guards, open-license policy) — see [CONTRIBUTING](../CONTRIBUTING.md) §5.
- [ ] Below-line (`ASIL-*`) changes exercise the re-validation gate in a test.
- [ ] Any default/reference content I added is open-source licensed.
