# Changelog

All notable changes to Loom are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it reaches a stable API.

## [Unreleased]

### Added
- **Eclipse Ankaios orchestrator.** A third `Orchestrator` implementation
  ([`AnkaiosOrchestrator`](loom/orchestrator/ankaios.py)) alongside in-process and
  Compose/KUKSA — the automotive workload orchestrator that replaces Docker-Compose without
  touching the bus or tick loop (verified equivalent to in-process against a fake control
  interface). [`loom/deploy/ankaios.py`](loom/deploy/ankaios.py) renders the Ankaios
  desired-state manifest (databroker + one workload per subsystem) from a composition, exposed
  as **`loom deploy <spec> [--target ankaios] [--out FILE]`**.
- **Transitive toolchain SBOM.** Alongside the module-level vehicle SBOM, `loom run`/`loom sbom`
  now emit `toolchain.cdx.json` — the installed transitive dependency closure of the Loom
  runtime (PURLs + licenses + edges), built from installed package metadata via
  [`loom/assurance/deps.py`](loom/assurance/deps.py). Covers the software-supply-chain axis the
  module-level bill does not; recorded in `run.json` `assurance.toolchainSbom`.
- **Per-module SBOMs.** Each contract's `sbomRef` (e.g. `sbom/bms.default.cdx.json`) now
  resolves to a real artifact: alongside the aggregate vehicle SBOM, `loom run` writes one
  CycloneDX SBOM per composed module under `runs/<id>/sbom/`, recorded in `run.json`'s
  `assurance.moduleSboms`. Previously the `sbomRef` references dangled (only the aggregate
  was generated). v0 scope is unchanged — module-level, not a transitive dependency scan.
- **`loom sbom <spec>` command.** Emits the vehicle + per-module SBOMs to a directory
  (`--out`, default `runs/sbom-<vehicle>/`) without running a simulation — for compliance
  pipelines and CI. See [docs/cli.md](docs/cli.md).
- **End-to-end `unit_consistency` demonstration.** A new `powertrain.custom_units` swap whose
  contract declares it reads `Vehicle.Speed` in **mph** while the plant publishes it in
  **km/h**, plus [`spec/vehicle.broken_units.yaml`](spec/vehicle.broken_units.yaml):
  `loom check` fails with one precise `unit_consistency` error — the real-composition
  counterpart to the synthetic checker fixtures.
- **Multi-contributor structure & documentation.** A full `docs/` set
  ([architecture](docs/architecture.md), [contracts](docs/contracts.md),
  [safety-model](docs/safety-model.md), [extending](docs/extending.md), [cli](docs/cli.md),
  [dashboard](docs/dashboard.md), [glossary](docs/glossary.md), index), plus
  [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md),
  and this changelog.
- **Continuous integration** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) — ruff
  + pytest on Linux and Windows for Python 3.12. PR and issue templates, CODEOWNERS.
- **Linting** — `ruff` config in `pyproject.toml` (E/W/F/I/B/UP) and a clean tree.

### Fixed
- **Reproducible installs.** `pyproject.toml` now declares `kuksa-client` (was imported by
  the distributed-orchestrator tests but undeclared), and the `dev` extra self-references
  `dashboard,compose` so `pip install -e ".[dev]"` alone makes the full suite importable.
- **Clean-checkout CI.** Installed the `dashboard` package (`packages.find` includes
  `dashboard*`) so the bare `pytest` console script — and `uvicorn dashboard.app:app` — work
  without the repo root on `sys.path`. CI (ruff + pytest on Linux & Windows) is green; the
  workflow uses `actions/checkout@v5` + `actions/setup-python@v6` (Node 24).
- Exception chaining in the CLI (`raise … from None`) and explicit `zip(strict=…)` at call
  sites, surfaced by the new linter.

### Changed
- The founding brief moved from `HANDOFF.md` (repo root) to
  [`docs/design-brief.md`](docs/design-brief.md), reframed as historical context; the living
  `docs/` are now authoritative. Code comments still cite it as "HANDOFF §N."

## [0.0.1] — 2026-06-27

Initial framework — the full **M0–M6** roadmap from the design brief, built and green
(129 tests). The end-to-end loop: **compose → validate → check → gate → simulate → monitor
→ assure**.

### Added
- **M0** — repo scaffold, composition + contract JSON Schemas, in-process VSS shim bus, the
  `loom` CLI.
- **M1** — five reference modules (`bms`, `powertrain`, `adas`, `hmi`, `body`) with real
  contracts, a longitudinal plant behind an FMI-style boundary, and a closed cross-module
  control loop over VSS signals (speed tracks the cycle, SoC drops).
- **M2** — the static composition checker (producer-uniqueness, signal-resolution, units,
  timing, assume/guarantee, **open-source license** policy) + composition report.
- **M3** — runtime contract monitors over a sandboxed safe-eval predicate layer, plus fault
  injection (`dropout`, `stuck`, `latency`, `crash`).
- **M4** — the safety-line swap gate: below-line (`ASIL-*`) swaps are refused without
  `--revalidate`; the baseline lives in a committed lock.
- **M5** — assurance generation: a CycloneDX vehicle SBOM and a GSN assurance-case skeleton,
  with goals that **defeat** when their evidence fails.
- **M6** — a higher-fidelity Motoquant plant (RK4 + thermal), a FastAPI + HTMX/Alpine
  dashboard (compose · run · view), and a distributed Compose/KUKSA orchestrator sharing the
  same `Bus` interface and tick loop as the in-process path.

### Security
- Path-traversal and name-injection guards on all untrusted input (dashboard spec paths,
  vehicle names, run ids); fail-safe gate on malformed locks; atomic lock writes; the
  whitelisted-AST predicate sandbox. Each milestone was adversarially reviewed and the
  confirmed findings fixed before release.

[Unreleased]: https://github.com/toto171/loom/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/toto171/loom/releases/tag/v0.0.1
