# M5 design — assurance + compliance generation

**Goal (HANDOFF §8 M5):** aggregate per-module CycloneDX SBOMs into a vehicle
SBOM; build a GSN assurance-case skeleton from contracts + check results; render
to Mermaid.
**Acceptance:** one `loom run` produces `vehicle.cdx.json`, `assurance.gsn.yaml`,
and a rendered GSN diagram in `runs/<id>/`; swapping a module visibly changes the
assurance skeleton.

This is **skeleton / starting-point** generation, never a certification artifact
(HANDOFF §10 principle 7, §11). The outputs are honest about their limits.

---

## 1. Vehicle SBOM (`loom/assurance/sbom.py`)

Built with `cyclonedx-python-lib` (already a dependency). For v0 the SBOM is a
**bill of modules**, not a transitive-dependency scan:

- One CycloneDX `Component` per resolved module: name = module id, version +
  `license` (SPDX, from the contract), a `bom-ref`, and the plant as a component.
- BOM `metadata.component` = the vehicle (composition name + class).
- Serialize to `runs/<id>/vehicle.cdx.json` (CycloneDX JSON, schema-valid).
- **Honest scope:** this lists the composed modules + their declared licenses
  (feeds UNECE R155/R156 + CRA SBOM obligations) — it does NOT yet resolve each
  module's transitive software dependencies. Stated in the file + README.

Per-module SBOMs: each contract's `sbomRef` (e.g. `sbom/bms.default.cdx.json`)
resolves to a real artifact. `build_module_sbom()` emits one single-component
CycloneDX BOM per module (rooted at the module, sharing `_module_component` with
the aggregate so the two agree); `write_vehicle_sboms()` writes the vehicle SBOM
plus each module's under `runs/<id>/sbom/`, recorded in `run.json`'s
`assurance.moduleSboms`. `loom sbom <spec>` produces the same bundle without a sim
run. Same v0 scope — module-level, not a transitive dependency tree.

## 2. GSN assurance-case skeleton (`loom/assurance/gsn.py`)

A Goal Structuring Notation argument, machine-readable YAML first, rendered to
Mermaid second. Node types: Goal (G), Strategy (S), Solution/evidence (Sn),
Context (C), Assumption (A), with `supportedBy` / `inContextOf` links.

Assembled from the composition + contracts + check results + run outcome:

- **G1** (top): "Vehicle `<name>` is acceptably safe within its declared ODD."
  - inContextOf **C1**: ODD / VSS release / vehicle class.
- **S1**: "Argue over each subsystem's safety contract and the composition checks."
  - **G-static**: "The composition is internally compatible." supportedBy
    **Sn-static**: the M2 check report (each rule PASS = evidence; FAIL would be a
    defeated goal).
  - **G-<module>** per module: "`<module>` (`<safetyLevel>`) meets its contract."
    - inContextOf its `assume` predicates (as **A** nodes).
    - supportedBy **Sn-monitor-<module>**: runtime monitor outcome (no violation
      = evidence; a violation defeats the goal and is shown).
  - **G-swap**: "Below-line swaps were re-validated." supportedBy the gate / lock
    re-validation record (M4).
- Emit `runs/<id>/assurance.gsn.yaml` (nodes + links) and
  `runs/<id>/assurance.gsn.mmd` (Mermaid graph; node shape per GSN type).

**"Swapping a module visibly changes the skeleton":** the per-module goals carry
the impl id + safety level + monitor evidence, so swapping `bms.default` ->
`bms.custom_x` changes `G-bms` (impl id) and flips `Sn-monitor-bms` from
"no violation" to the `soc_estimate_drift` violation — a visibly different (and
now partially *defeated*) argument. The run report should note defeated goals.

## 3. Wiring

`loom run` already produces the M2 check report + M3 violations + M4 gate result.
After a run, generate the SBOM + GSN from those in-memory results (no re-compute)
and write the three files into `runs/<id>/`. Add a one-line summary to `run.json`
(`assurance: {goals, defeatedGoals, sbomComponents}`) and print the paths.

## 4. Files
- `loom/assurance/sbom.py` (CycloneDX aggregation) — replaces the stub.
- `loom/assurance/gsn.py` (GSN node model + builder + Mermaid renderer).
- `loom/assurance/__init__.py` — export, drop the "deferred" stub note.
- `loom/cli.py` — generate + write the three artifacts; summary + printed paths.
- tests: SBOM is valid CycloneDX with one component per module + correct licenses;
  GSN has the expected goals; a defeated goal appears when a monitor trips
  (custom_x); swapping the BMS changes the GSN; Mermaid renders.

## Known simplifications (honest scoping)
- SBOM is module-level (declared licenses), not a transitive dependency graph.
- GSN is a generated *skeleton* — the argument structure + evidence pointers, not
  a reviewed, complete, or certified safety case.
- No claim of type approval / certification anywhere in the outputs.
