"""Loom web dashboard (M6) — FastAPI + HTMX/Alpine.

Browse the module catalog, assemble a composition and launch a run, and view the
run's report / trace / monitor violations / GSN assurance / SBOM in the browser.
Runs go through the same `loom.run.execute_run` pipeline as the CLI (static check
-> safety-line gate -> sim -> assurance), so the dashboard inherits the gate and
the assurance behavior. Start with:  uvicorn dashboard.app:app --reload
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from loom import __version__, catalog
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.contracts.checker import check_composition
from loom.contracts.report import render_report
from loom.errors import GateRefused, LoomError, StaticCheckFailed
from loom.paths import repo_root, runs_dir
from loom.plant.loader import load_plant
from loom.run import execute_run
from loom.sim.stimulus import ScenarioStimulus

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app = FastAPI(title="Loom dashboard")


def _page(request: Request, name: str, ctx: dict, status_code: int = 200):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _safe_name(raw: str | None) -> str:
    """A schema-valid vehicle name (matches composition.schema.json metadata.name):
    no path separators or special chars that could inject into run-dir/lock paths."""
    s = re.sub(r"[^A-Za-z0-9 ._-]", "-", (raw or "").strip())
    s = re.sub(r"^[^A-Za-z0-9]+", "", s)
    return s[:64] or "composed-vehicle"


def _composed_spec_path(name: str) -> Path:
    d = runs_dir() / ".composed"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "vehicle"
    return d / f"{safe}.yaml"


def _spec_in_dir(spec: str) -> Path | None:
    """Resolve a spec filename within spec/, rejecting path traversal."""
    spec_dir = (repo_root() / "spec").resolve()
    target = (spec_dir / spec).resolve()
    return target if target.is_relative_to(spec_dir) else None


def _do_run(request: Request, spec_path: Path, scenario: str | None, revalidate: bool):
    """Execute a run; redirect to its detail page, or render the failure."""
    try:
        outcome = execute_run(spec_path, scenario or None, revalidate)
    except StaticCheckFailed as exc:
        return _page(request, "error.html", {
            "title": "Static check failed", "detail": render_report(exc.report),
            "spec": str(spec_path), "scenario": scenario, "show_revalidate": False,
        }, status_code=422)
    except GateRefused as exc:
        return _page(request, "error.html", {
            "title": "Safety-line swap gate refused", "detail": exc.decision.refused_reason,
            "spec": str(spec_path), "scenario": scenario, "show_revalidate": True,
        }, status_code=409)
    except LoomError as exc:
        return _page(request, "error.html", {
            "title": "Run failed", "detail": str(exc),
            "spec": str(spec_path), "scenario": scenario, "show_revalidate": False,
        }, status_code=400)
    except Exception as exc:  # never leak a stack trace to the browser
        return _page(request, "error.html", {
            "title": "Unexpected error", "detail": f"{type(exc).__name__}: {exc}",
            "spec": None, "scenario": None, "show_revalidate": False,
        }, status_code=500)
    return RedirectResponse(url=f"/runs/{outcome.run_id}", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _page(request, "home.html", {
        "version": __version__,
        "subsystems": catalog.list_subsystems(),
        "specs": catalog.list_specs(),
        "scenarios": catalog.list_scenarios(),
        "runs": catalog.list_runs(limit=12),
    })


@app.get("/compose", response_class=HTMLResponse)
def compose(request: Request):
    return _page(request, "compose.html", {
        "subsystems": catalog.list_subsystems(),
        "plants": catalog.list_plants(),
        "scenarios": catalog.list_scenarios(),
    })


@app.post("/run/spec")
def run_spec(request: Request, spec: str = Form(...), scenario: str = Form(""),
             revalidate: bool = Form(False)):
    target = _spec_in_dir(spec)
    if target is None:
        return _page(request, "error.html", {
            "title": "Invalid spec", "detail": spec,
            "spec": None, "scenario": None, "show_revalidate": False,
        }, status_code=400)
    return _do_run(request, target, scenario, revalidate)


@app.post("/run/revalidate")
def run_revalidate(request: Request, spec_path: str = Form(...), scenario: str = Form("")):
    """Re-run a refused spec with --revalidate. Confine the path to the only two dirs
    the legitimate refused-run flow can produce: spec/ and runs/.composed/."""
    target = Path(spec_path).resolve()
    spec_dir = (repo_root() / "spec").resolve()
    composed_dir = (runs_dir() / ".composed").resolve()
    if not (target.is_relative_to(spec_dir) or target.is_relative_to(composed_dir)):
        return _page(request, "error.html", {
            "title": "Invalid spec path", "detail": spec_path,
            "spec": None, "scenario": None, "show_revalidate": False,
        }, status_code=400)
    return _do_run(request, target, scenario, revalidate=True)


@app.post("/run/compose")
async def run_compose(request: Request):
    form = await request.form()
    name = _safe_name(form.get("vehicle_name"))
    subsystems = {}
    for sub in catalog.list_subsystems():
        impl = form.get(f"impl_{sub}")
        if impl and impl != "(omit)":
            subsystems[sub] = {"impl": impl}
    spec_dict = {
        "apiVersion": "loom/v0",
        "kind": "Vehicle",
        "metadata": {"name": name, "vehicleClass": str(form.get("vehicle_class") or "M1")},
        "plant": {"impl": str(form.get("plant") or "longitudinal"),
                  "params": {"massKg": 1500, "wheelRadiusM": 0.31, "batteryKwh": 40}},
        "bus": {"type": "vss", "vssRelease": "v4.0"},
        "subsystems": subsystems,
        "scenarios": [str(form.get("scenario") or "urban_drive")],
    }
    spec_path = _composed_spec_path(name)
    spec_path.write_text(yaml.safe_dump(spec_dict, sort_keys=False), encoding="utf-8")
    return _do_run(request, spec_path, str(form.get("scenario") or ""), bool(form.get("revalidate")))


@app.get("/check", response_class=HTMLResponse)
def check(spec: str):
    """HTMX partial: the static-check report for an existing spec (as a <pre>)."""
    target = _spec_in_dir(spec)
    if target is None:
        return "<pre>invalid spec path</pre>"
    try:
        comp = load_composition(target)
        plant = load_plant(comp.plant_impl, comp.plant_params)
        modules = resolve_modules(comp)
        report = check_composition(comp.name, modules, plant=plant,
                                  stimulus_provides=ScenarioStimulus.provides)
    except LoomError as exc:
        return f"<pre>check failed: {escape(str(exc))}</pre>"
    except Exception as exc:
        return f"<pre>check error: {escape(type(exc).__name__)}</pre>"
    return f"<pre>{escape(render_report(report))}</pre>"


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request):
    return _page(request, "runs.html", {"runs": catalog.list_runs()})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    summary = catalog.load_run(run_id)
    if summary is None:
        return _page(request, "error.html", {
            "title": "Run not found", "detail": run_id,
            "spec": None, "scenario": None, "show_revalidate": False,
        }, status_code=404)
    mmd_path = catalog.run_artifact(run_id, "assurance.gsn.mmd")
    report_path = catalog.run_artifact(run_id, "composition_report.txt")
    return _page(request, "run_detail.html", {
        "run": summary,
        "gsn_mermaid": mmd_path.read_text(encoding="utf-8") if mmd_path else "",
        "report_text": report_path.read_text(encoding="utf-8") if report_path else "",
    })
