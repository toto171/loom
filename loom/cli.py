"""The ``loom`` command-line interface."""
from __future__ import annotations

from pathlib import Path

import typer
import yaml

from loom import __version__
from loom.assurance.sbom import write_vehicle_sboms
from loom.compose.loader import load_composition, validate_composition_data
from loom.compose.resolve import resolve_modules
from loom.contracts.checker import check_composition
from loom.contracts.report import render_report
from loom.errors import GateRefused, LoomError, StaticCheckFailed
from loom.paths import runs_dir
from loom.plant.loader import load_plant
from loom.run import execute_run
from loom.sim.stimulus import ScenarioStimulus

app = typer.Typer(
    add_completion=False,
    help="Loom — compose, validate, check, and simulate vehicles.",
    no_args_is_help=True,
)


@app.command()
def validate(
    spec: Path = typer.Argument(..., help="Path to a vehicle composition spec.")
) -> None:
    """Validate a composition spec against the JSON Schema."""
    try:
        data = yaml.safe_load(Path(spec).read_text(encoding="utf-8"))
    except FileNotFoundError:
        typer.secho(f"spec not found: {spec}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(2) from None

    errors = validate_composition_data(data)
    if errors:
        typer.secho(f"INVALID  {spec}", fg=typer.colors.RED, bold=True)
        for err in errors:
            typer.echo(f"  - {err}")
        raise typer.Exit(1)
    typer.secho(f"OK       {spec}", fg=typer.colors.GREEN, bold=True)


@app.command()
def check(
    spec: Path = typer.Argument(..., help="Path to a vehicle composition spec.")
) -> None:
    """Run the static composition checker (signals, units, timing, assumptions, license)."""
    try:
        comp = load_composition(spec)
        plant = load_plant(comp.plant_impl, comp.plant_params)
        modules = resolve_modules(comp)
    except LoomError as exc:
        typer.secho(f"check failed: {exc}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(2) from None

    report = check_composition(
        comp.name, modules, plant=plant, stimulus_provides=ScenarioStimulus.provides
    )
    typer.echo(render_report(report))
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to a vehicle composition spec."),
    scenario: str = typer.Option(
        None, "--scenario", "-s", help="Scenario name (defaults to the first in the spec)."
    ),
    revalidate: bool = typer.Option(
        False, "--revalidate", help="Acknowledge + record a below-the-safety-line (ASIL-*) implementation swap."
    ),
) -> None:
    """Compose -> static check -> safety-line gate -> drive -> trace + report + assurance."""
    try:
        outcome = execute_run(
            spec, scenario, revalidate,
            on_notice=lambda m: typer.secho(m, fg=typer.colors.YELLOW),
        )
    except StaticCheckFailed as exc:
        typer.secho(f"static check FAILED for {spec} — aborting run", fg=typer.colors.RED, bold=True)
        typer.echo(render_report(exc.report))
        raise typer.Exit(1) from None
    except GateRefused as exc:
        typer.secho(f"swap gate REFUSED for {spec}", fg=typer.colors.RED, bold=True)
        typer.echo(exc.decision.refused_reason)
        typer.echo("re-run with --revalidate to acknowledge and record the swap.")
        raise typer.Exit(3) from None
    except LoomError as exc:
        typer.secho(f"run failed: {exc}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(1) from None

    s = outcome.summary
    out = outcome.run_dir
    typer.secho(f"run {outcome.run_id}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  modules : {', '.join(s['modules'])}")
    typer.echo(f"  scenario: {s['scenario']}  ({s['steps']} steps, {s['durationS']:g}s)")
    if outcome.decision.swaps:
        tag = "re-validated below-line" if outcome.revalidation else "swapped"
        typer.secho(
            f"  swaps ({tag}): {'; '.join(sw.describe() for sw in outcome.decision.swaps)}",
            fg=typer.colors.MAGENTA,
        )
    if s["changedSignals"]:
        typer.secho(f"  signals changed ({len(s['changedSignals'])}):", fg=typer.colors.GREEN)
        for path, fl in s["changedSignals"].items():
            typer.echo(f"    {path}: {fl['first']} -> {fl['last']}")
    else:
        typer.secho("  no signals changed", fg=typer.colors.YELLOW)
    if s["violations"]:
        typer.secho(f"  monitor violations ({len(s['violations'])}):", fg=typer.colors.RED)
        for v in s["violations"]:
            typer.echo(f"    [{v['firstT']:g}-{v['lastT']:g}s] {v['message']}")
    else:
        typer.secho("  monitor violations: none", fg=typer.colors.GREEN)
    typer.echo(f"  trace   : {out / 'trace.jsonl'}")
    typer.echo(f"  report  : {out / 'composition_report.txt'}")
    typer.echo(
        f"  sbom    : {out / 'vehicle.cdx.json'} ({s['assurance']['sbomComponents']} components, "
        f"{len(s['assurance']['moduleSboms'])} per-module)"
    )
    if outcome.gsn.defeated:
        typer.secho(
            f"  assurance: {out / 'assurance.gsn.yaml'}  (DEFEATED goals: {', '.join(s['assurance']['defeatedGoals'])})",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.echo(f"  assurance: {out / 'assurance.gsn.yaml'} (all goals supported)")


@app.command()
def sbom(
    spec: Path = typer.Argument(..., help="Path to a vehicle composition spec."),
    out: Path = typer.Option(
        None, "--out", "-o", help="Output directory (default: runs/sbom-<vehicle>/)."
    ),
) -> None:
    """Generate the vehicle + per-module CycloneDX SBOMs (no sim run)."""
    try:
        comp = load_composition(spec)
        modules = resolve_modules(comp)
    except LoomError as exc:
        typer.secho(f"sbom failed: {exc}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(2) from None

    out_dir = out or (runs_dir() / f"sbom-{comp.name}")
    result = write_vehicle_sboms(out_dir, comp.name, comp.vehicle_class, modules, comp.plant_impl)
    typer.secho(f"sbom {comp.name}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  vehicle : {out_dir / result['vehicle']}")
    typer.secho(f"  modules : {len(result['modules'])} per-module SBOM(s)", fg=typer.colors.GREEN)
    for ref in result["modules"]:
        typer.echo(f"    {out_dir / ref}")


@app.command()
def version() -> None:
    """Print the Loom version."""
    typer.echo(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
