# Loom documentation

Start here. The docs are layered — read top to bottom if you're new, or jump to the task.

## Orientation

| Doc | Read it to… |
|---|---|
| [architecture.md](architecture.md) | understand the pipeline, the swappable abstractions, and the repo layout. **Start here.** |
| [glossary.md](glossary.md) | decode VSS, FMI, GSN, SBOM, ASIL, QM, ODD, SOTIF, KUKSA, … |

## Working with Loom

| Doc | Read it to… |
|---|---|
| [contracts.md](contracts.md) | author/change a `vehicle.yaml` or a `contract.yaml` (the two core schemas) and understand the checker. |
| [safety-model.md](safety-model.md) | understand the safety line, the swap gate, the lock, and the trust model. |
| [cli.md](cli.md) | use `loom validate / check / run` (flags, exit codes). |
| [dashboard.md](dashboard.md) | run and understand the web UI. |

## Contributing

| Doc | Read it to… |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | set up the dev environment, run tests/lint, and follow the conventions. |
| [extending.md](extending.md) | add a subsystem, plant, scenario, or checker rule. |
| [../SECURITY.md](../SECURITY.md) | report a vulnerability / see the security posture. |

## Background & history

| Doc | Read it to… |
|---|---|
| [design-brief.md](design-brief.md) | read the **founding handoff brief** — the "why now," the standards landscape, schema intent, and milestone acceptance criteria. Code comments cite it as "HANDOFF §N." |
| [m1-design.md](m1-design.md) · [m3-design.md](m3-design.md) · [m5-design.md](m5-design.md) | per-milestone design notes for the cross-module loop, runtime monitors, and assurance generation. |

> **Authority of these docs.** The living docs in this directory describe the *as-built*
> system and take precedence over the design brief where they differ. The brief is preserved
> for rationale and history, not as the current spec.
