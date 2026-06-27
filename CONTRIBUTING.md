# Contributing to Loom

Welcome. This guide gets you from clone to green tests, then explains the conventions and
the review bar. If anything here is wrong or unclear, fixing it is a great first PR.

> New to the codebase? Read [docs/architecture.md](docs/architecture.md) first, then come
> back here. To add a subsystem/plant/scenario, see [docs/extending.md](docs/extending.md).

---

## 1. Development environment

**Requirements:** Python **3.12+** and Git. (Docker is only needed for the live KUKSA
databroker path — everything else, including the full test suite, runs without it.)

```bash
git clone https://github.com/toto171/loom.git
cd loom

python -m venv .venv
# Activate: POSIX → source .venv/bin/activate   |   Windows → .venv\Scripts\activate

pip install -e ".[dev]"      # the package + dashboard + compose + pytest + ruff
```

`.[dev]` self-references `.[dashboard,compose]`, so this single install pulls **everything
the test suite imports** (FastAPI for the dashboard tests, kuksa-client for the distributed
orchestrator tests). If you install only the bare package, those tests can't run.

Optional feature-only extras (already included in `dev`):

| Extra | Pulls | For |
|---|---|---|
| `.[dashboard]` | fastapi, uvicorn, jinja2, python-multipart | the [web UI](docs/dashboard.md) |
| `.[compose]` | kuksa-client | the [distributed orchestrator](docs/architecture.md#3-the-swappable-abstractions) |

Verify your setup:

```bash
pytest                                   # full suite — should be all green
loom run spec/vehicle.example.yaml -s urban_drive   # the CLI works end-to-end
```

---

## 2. The inner loop

| Task | Command |
|---|---|
| Run all tests | `pytest` |
| Run one test file | `pytest tests/test_m4_gate.py` |
| Lint | `ruff check .` |
| Auto-fix lint (imports, simple rules) | `ruff check . --fix` |
| Run the CLI | `loom check spec/vehicle.example.yaml` |
| Run the dashboard | `uvicorn dashboard.app:app --reload` |

**Both `ruff check .` and `pytest` must pass before you push** — CI runs exactly these on
Linux and Windows (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Keeping the
suite fast (it runs in a few seconds) is a feature; please keep new tests deterministic and
offline.

---

## 3. Code conventions

- **Style is enforced by ruff** (config in [`pyproject.toml`](pyproject.toml)): pycodestyle
  (E/W), pyflakes (F), import-sorting (I), bugbear (B), pyupgrade (UP). Line length is 100
  (not gated — there's no autoformatter in-tree yet; keep lines reasonable). Run
  `ruff check . --fix` and it sorts your imports for you.
- **Type hints** on public functions; `from __future__ import annotations` at the top of
  modules (the codebase uses it throughout).
- **Docstrings** explain *why*, and call out honest scope. Many modules cite the founding
  brief as `HANDOFF §N` → that's [docs/design-brief.md](docs/design-brief.md); keep the
  convention when you're implementing something it specified.
- **Interface-first.** New behavior is usually a new *implementation* behind an existing
  abstraction (`Bus`, `Plant`, `Orchestrator`, `Module`), not a change to the abstraction.
  See [docs/extending.md](docs/extending.md).
- **Honest scoping is a value, not a disclaimer.** If something is a skeleton, a proxy, or a
  simplification, say so in the code and the docs — the way the existing "Known
  simplifications" / "Honest scope" notes do. Loom generates assurance *skeletons*, never
  certification; never let code or docs imply otherwise.

---

## 4. Testing conventions

- **Every checker rule and every feature ships with a passing *and* a failing test.** This
  is the project's founding rule (design brief §6) — a rule with no failing fixture isn't
  done. Checker fixtures live in [`tests/test_m2_checker.py`](tests/test_m2_checker.py).
- **Milestone acceptance is automated.** The `test_m*` files encode the acceptance criteria
  from [docs/design-brief.md](docs/design-brief.md) §8 — don't regress them.
- **Safety-critical paths get extra coverage.** Changes to the gate, the lock, the
  predicate safe-eval, or the path-handling guards need tests that exercise the *refusal* /
  *rejection* path, not just the happy path. The dashboard's untrusted-input guards
  (path traversal, name injection) are regression-tested in `test_m6_dashboard.py` — keep
  them that way.

---

## 5. Safety & security discipline (don't weaken these)

These are the load-bearing invariants. A PR that touches them gets close review:

- **The safety line is enforced, never bypassed.** A below-line (`ASIL-*`) swap must remain
  gated; don't add a code path that lets one through without `--revalidate`. See
  [docs/safety-model.md](docs/safety-model.md).
- **Locks are committed state.** `locks/` is versioned on purpose (so deleting `runs/` can't
  reset a baseline). Don't gitignore it.
- **The predicate layer stays sandboxed.** `loom/monitors/predicate.py` is a whitelisted-AST
  evaluator — no `eval`, no builtins, no attribute access. Don't add escapes.
- **Untrusted input stays confined.** Spec paths, vehicle names, and run ids are validated
  before they touch the filesystem. Keep the guards and their tests.
- **Default/reference content is open-source.** Every default module's `contract.license`
  must be an OSI/SPDX id — the checker enforces this, and so does review.

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a public issue
for it.

---

## 6. Git & pull requests

- **Branch** off `main`: `feature/<short-name>`, `fix/<short-name>`, or `docs/<short-name>`.
- **Commits** are imperative and scoped (`gate: fail-safe on missing safetyLevel`). Group
  related changes; keep unrelated ones in separate PRs.
- **Open a PR** with: what changed and why, how you tested it, and any scope you
  deliberately left out. The [PR template](.github/pull_request_template.md) prompts for
  this. Fill the checklist.
- **CI must be green** (ruff + pytest on Linux and Windows) before merge.
- This repo was built with substantial AI assistance and each milestone was **adversarially
  reviewed** (independent agents trying to break it). You're encouraged to review in that
  spirit — try to falsify a change, not just confirm it. If you used an AI assistant for a
  commit, the `Co-Authored-By:` trailer is welcome.

---

## 7. Code of Conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Be the kind of
collaborator you'd want on a safety-tooling project.
