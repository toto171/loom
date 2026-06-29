# CLI reference — `loom`

The `loom` command is defined in [`loom/cli.py`](../loom/cli.py) (Typer) and installed by
`pip install -e .`. The `validate`, `check`, `run`, and `sbom` commands take a path to a
composition spec ([`vehicle.yaml`](contracts.md)); `version` takes no arguments.

```
loom validate <spec>                 # JSON-Schema validation only
loom check    <spec>                 # static contract check + report
loom run      <spec> [--scenario S] [--revalidate]
loom sbom     <spec> [--out DIR]     # vehicle + per-module CycloneDX SBOMs (no sim)
loom version
```

Run `loom --help` or `loom <command> --help` for the generated usage.

---

## `loom validate <spec>`

Validates the spec against [`composition.schema.json`](../spec/schema/composition.schema.json).
Schema only — does not resolve modules.

| Exit | Meaning |
|---|---|
| 0 | valid |
| 1 | schema-invalid (each error printed) |
| 2 | spec file not found |

---

## `loom check <spec>`

Resolves the modules + plant and runs the [static checker](contracts.md#3-the-static-checker)
(producer-uniqueness, signal-resolution, units, timing, assume/guarantee, license), printing
the composition report (signal graph + per-rule results).

| Exit | Meaning |
|---|---|
| 0 | all rules pass |
| 1 | a rule failed (the report shows which) |
| 2 | load/resolution error (bad YAML, missing module, …) |

```bash
loom check spec/vehicle.example.yaml     # passes, emits the report
loom check spec/vehicle.broken.yaml      # fails with a precise unresolved-signal message
```

---

## `loom run <spec> [--scenario S] [--revalidate]`

The full pipeline: compose → validate → static check → **safety-line gate** → simulate
(modules + plant + driver + faults + monitors) → assurance. Writes `runs/<id>/` (see
[architecture.md §6](architecture.md#6-artifacts-of-a-run)).

| Option | Default | Meaning |
|---|---|---|
| `--scenario`, `-s` | first scenario in the spec | which scenario to drive |
| `--revalidate` | off | acknowledge + record a below-the-line (`ASIL-*`) swap |

| Exit | Meaning |
|---|---|
| 0 | ran (the summary prints changed signals, violations, and artifact paths) |
| 1 | static check failed (report printed) **or** a run error |
| 3 | **swap gate refused** — re-run with `--revalidate` |

```bash
loom run spec/vehicle.example.yaml --scenario urban_drive          # nominal drive
loom run spec/vehicle.example.yaml --scenario sensor_dropout_test  # trips a BMS monitor
loom run spec/vehicle.swap_bms.yaml                                # below-line swap -> exit 3
loom run spec/vehicle.swap_bms.yaml --revalidate                   # acknowledged -> runs
loom run spec/vehicle.swap_hmi.yaml                                # QM swap -> free, no gate
loom run spec/vehicle.motoquant.yaml                               # higher-fidelity plant swap
```

The exit codes are stable, so the same `loom run` drives both CI and the
[dashboard](dashboard.md) (which maps exit 3 → HTTP 409).

---

## `loom sbom <spec> [--out DIR]`

Generates the CycloneDX SBOMs for a composition **without** running a simulation — the
aggregate vehicle SBOM (`vehicle.cdx.json`) plus one per-module SBOM under `sbom/`
(`sbom/<module>.cdx.json`, the artifact each contract's [`sbomRef`](contracts.md) points at).
Intended for compliance pipelines and CI that need the bill of modules + declared licenses
on its own. Scope matches `loom run`: module-level, not a transitive dependency scan.

| Option | Default | Meaning |
|---|---|---|
| `--out`, `-o` | `runs/sbom-<vehicle>/` | output directory |

| Exit | Meaning |
|---|---|
| 0 | SBOMs written (paths printed) |
| 2 | load/resolution error (bad YAML, missing module, …) |

```bash
loom sbom spec/vehicle.example.yaml                 # -> runs/sbom-toy-ev-l7/
loom sbom spec/vehicle.example.yaml --out build/sbom
```

---

## `loom version`

Prints the package version (`loom.__version__`).
