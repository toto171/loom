"""Shared run pipeline used by both the CLI and the web dashboard.

`execute_run` performs the full HANDOFF §4 flow — parse + validate, fail-fast
static check, safety-line gate, bring up + drive the in-process sim, and generate
the trace + composition report + lock/re-validation + SBOM + GSN assurance — and
returns a structured RunOutcome. Failures are raised as domain exceptions
(StaticCheckFailed, GateRefused, LoomError) so each front-end renders them itself.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from loom.assurance.gsn import Gsn, build_gsn, render_mermaid
from loom.assurance.sbom import build_vehicle_sbom, sbom_component_count
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.model import Composition
from loom.compose.resolve import ResolvedModule, resolve_modules
from loom.contracts.checker import CheckReport, check_composition
from loom.contracts.report import render_report
from loom.errors import GateRefused, StaticCheckFailed
from loom.monitors.engine import MonitorEngine
from loom.orchestrator.base import RunResult
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import locks_dir, runs_dir
from loom.plant.loader import load_plant
from loom.safety.gate import GateDecision, current_config, detect_swaps, gate, load_lock, write_lock
from loom.sim.faults import FaultInjector
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus
from loom.sim.trace import Trace


@dataclass
class RunOutcome:
    run_id: str
    run_dir: Path
    composition: Composition
    scenario_name: str
    modules: list[ResolvedModule]
    report: CheckReport
    result: RunResult
    gsn: Gsn
    sbom_json: str
    summary: dict
    decision: GateDecision
    revalidation: dict | None


def execute_run(
    spec: str | Path,
    scenario: str | None = None,
    revalidate: bool = False,
    *,
    on_notice: Callable[[str], None] | None = None,
) -> RunOutcome:
    spec = Path(spec)
    comp = load_composition(spec)
    scenario_name = scenario or comp.scenarios[0]
    scen = load_scenario(scenario_name)
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)

    # Fail-fast static contract check (HANDOFF §4 step 2).
    report = check_composition(
        comp.name, modules, plant=plant, stimulus_provides=ScenarioStimulus.provides
    )
    if not report.ok:
        raise StaticCheckFailed(report)

    # Safety-line swap gate (HANDOFF §5.2 / §8 M4).
    lock_path = locks_dir() / f"{comp.name}.lock.json"
    lock = load_lock(lock_path)
    current = current_config(modules)
    if lock is None:
        below = [m.module_id for m in modules if m.contract.is_below_safety_line]
        if below and on_notice:
            on_notice(
                f"establishing safety baseline for '{comp.name}' (trust-on-first-use; "
                f"{len(below)} below-line module(s): {', '.join(below)})"
            )
    decision = gate(detect_swaps(current, lock), revalidate)
    if not decision.allowed:
        raise GateRefused(decision)

    bus = ShimBus()
    trace = Trace()
    monitors = MonitorEngine.from_modules(modules)
    result = InProcessOrchestrator().run(
        modules=[m.instance for m in modules],
        bus=bus,
        plant=plant,
        scenario=scen,
        trace=trace,
        stimulus=ScenarioStimulus(scen),
        faults=FaultInjector(scen.faults),
        monitors=monitors,
    )

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_id = f"{stamp}-{comp.name}"
    out = runs_dir() / run_id
    out.mkdir(parents=True, exist_ok=True)
    trace.write_jsonl(out / "trace.jsonl")
    (out / "composition_report.txt").write_text(render_report(report), encoding="utf-8")

    write_lock(lock_path, comp.name, current)
    revalidation = None
    if decision.gated_swaps:
        revalidation = {
            "vehicle": comp.name,
            "runId": run_id,
            "revalidatedSwaps": [
                {
                    "subsystem": s.subsystem, "from": s.old_impl, "to": s.new_impl,
                    "oldSafetyLevel": s.old_safety_level, "newSafetyLevel": s.new_safety_level,
                }
                for s in decision.gated_swaps
            ],
        }
        (out / "revalidation.json").write_text(json.dumps(revalidation, indent=2), encoding="utf-8")

    sbom_json = build_vehicle_sbom(comp.name, comp.vehicle_class, modules, comp.plant_impl)
    (out / "vehicle.cdx.json").write_text(sbom_json, encoding="utf-8")
    gsn = build_gsn(
        comp, modules, report, result.violations,
        revalidated_swaps=decision.gated_swaps if revalidation else None,
    )
    (out / "assurance.gsn.yaml").write_text(yaml.safe_dump(gsn.to_dict(), sort_keys=False), encoding="utf-8")
    (out / "assurance.gsn.mmd").write_text(render_mermaid(gsn), encoding="utf-8")

    violations = result.violations
    if violations:
        with (out / "violations.jsonl").open("w", encoding="utf-8") as fh:
            for v in violations:
                fh.write(json.dumps(v.__dict__) + "\n")

    windows: dict[tuple, list[float]] = {}
    for v in violations:
        windows.setdefault((v.module, v.monitor_id, v.kind, v.message), []).append(v.t)

    summary = {
        "runId": run_id,
        "spec": str(spec),
        "vehicle": comp.name,
        "vehicleClass": comp.vehicle_class,
        "scenario": scen.name,
        "orchestrator": result.orchestrator,
        "plant": comp.plant_impl,
        "staticCheck": {"ok": report.ok, "warnings": len(report.warnings)},
        "swaps": [s.describe() for s in decision.swaps],
        "revalidation": revalidation,
        "assurance": {
            "sbomComponents": sbom_component_count(modules, comp.plant_impl),
            "goals": sum(1 for n in gsn.nodes if n.type == "goal"),
            "defeatedGoals": [n.id for n in gsn.defeated],
        },
        "modules": [m.module_id for m in modules],
        "steps": result.steps,
        "durationS": result.duration_s,
        "skippedMonitors": monitors.skipped,
        "violations": [
            {"module": k[0], "monitor": k[1], "kind": k[2], "message": k[3],
             "firstT": min(ts), "lastT": max(ts), "ticks": len(ts)}
            for k, ts in windows.items()
        ],
        "changedSignals": {
            path: {"first": first, "last": last}
            for path, (first, last) in result.changed_signals.items()
        },
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return RunOutcome(
        run_id=run_id, run_dir=out, composition=comp, scenario_name=scen.name,
        modules=modules, report=report, result=result, gsn=gsn, sbom_json=sbom_json,
        summary=summary, decision=decision, revalidation=revalidation,
    )
