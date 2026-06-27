# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report it privately through GitHub's **[private vulnerability reporting](https://github.com/toto171/loom/security/advisories/new)**
(the repository's *Security → Report a vulnerability* tab). Include:

- a description and the impact,
- steps to reproduce (a spec / scenario / request that triggers it),
- affected version or commit.

We'll acknowledge the report, investigate, and coordinate a fix and disclosure. Thank you
for helping keep Loom safe.

## Supported versions

Loom is pre-1.0; only the latest `main` / most recent `0.0.x` is supported.

## Scope and threat model

Loom is **development and validation tooling**, not a certified in-vehicle runtime and not a
hardened multi-tenant service. The defenses below exist because the tool ingests untrusted
artifacts (composition specs, contracts, scenarios) and the dashboard accepts untrusted form
input — but the dashboard ships **without authentication or rate limiting** and should be run
locally or behind your own access control, not exposed to the public internet.

In scope (please report):

- **Path traversal / injection** via spec paths, vehicle names, run ids, or contract/scenario
  content that escapes `spec/`, `runs/`, or `locks/`.
- **Predicate sandbox escape** — getting `loom/monitors/predicate.py` to execute anything
  beyond its whitelisted AST (no `eval`, no builtins, no attribute access by design).
- **Safety-gate bypass** — making a below-line (`ASIL-*`) swap run without `--revalidate`,
  or resetting a baseline without it being visible.
- Denial of service from a malformed but schema-valid spec/contract/scenario.

Out of scope:

- Lack of auth/rate-limiting on the dashboard (known; run it locally).
- Anything implying the generated SBOM/GSN constitute certification (they don't — by design).

## Security posture (what's already hardened)

Each milestone was adversarially reviewed; confirmed findings were fixed with regression
tests. Current defenses include: untrusted-input confinement (`_safe_name`, `_spec_in_dir`,
traversal-guarded `load_run`), the whitelisted-AST predicate evaluator, the fail-safe swap
gate (a malformed lock gates rather than passes), atomic lock writes, and a committed
(non-gitignored) safety baseline so generated state can't silently reset it. The
corresponding tests live in `tests/test_m4_gate.py`, `tests/test_m6_dashboard.py`, and
`tests/test_predicate.py`.
