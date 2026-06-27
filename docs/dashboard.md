# Web dashboard (M6)

A FastAPI + HTMX/Alpine UI to browse the catalog, assemble a composition, launch a run, and
view its report / GSN assurance / SBOM — all through the **same** `execute_run` pipeline as
the CLI, so the browser inherits the static check and the safety-line gate. Code lives in
[`dashboard/`](../dashboard).

## Run it

```bash
pip install -e ".[dashboard]"          # fastapi, uvicorn, jinja2, python-multipart
uvicorn dashboard.app:app              # http://127.0.0.1:8000
# add --reload for autoreload during development
```

(`.[dev]` already includes `.[dashboard]`, so a dev install needs nothing extra.)

## Routes

| Method + path | Purpose |
|---|---|
| `GET /` | home — catalog of subsystems, impls, plants, scenarios, specs |
| `GET /compose` | the compose form (pick impls/plant/scenario, name the vehicle) |
| `POST /run/spec` | run an existing spec file |
| `POST /run/compose` | run a composition assembled in the form |
| `POST /run/revalidate` | re-run acknowledging a below-line swap (the `--revalidate` path) |
| `GET /check` | static-check partial for a spec (HTMX fragment) |
| `GET /runs` | list past runs |
| `GET /runs/{run_id}` | run detail — report, GSN (rendered via Mermaid), SBOM |

The read-only catalog/run data comes from [`loom/catalog.py`](../loom/catalog.py); the
run/check actions call into [`loom/run.py`](../loom/run.py) and
[`loom/contracts/checker.py`](../loom/contracts/checker.py).

## Behavior it inherits

Because every action goes through `execute_run`, the dashboard cannot diverge from the CLI:

- A below-line swap without re-validation returns **HTTP 409** ("gate refused"); re-running
  via `/run/revalidate` proceeds — the gate, in the browser.
- A failing static check surfaces the same report.
- Each run writes the same `runs/<id>/` artifacts.

See [`tests/test_m6_dashboard.py`](../tests/test_m6_dashboard.py) for the end-to-end and
gate-inheritance tests.

## Security notes

The dashboard takes untrusted form input, so it is defensive by construction (these are
regression-tested):

- **Vehicle names are sanitized** (`_safe_name`) before they touch the filesystem, so a
  crafted name cannot escape `locks/` or `runs/` (path-injection defense).
- **Spec paths are confined** (`_spec_in_dir`) to `spec/`, so `?spec=../…` cannot read
  arbitrary files; `/check` rejects traversal with "invalid spec path".
- **`load_run` is traversal-guarded** — a `run_id` that resolves outside `runs/` returns
  nothing.

These are validation/dev tooling defaults; the dashboard is not hardened for untrusted
public exposure (no auth, no rate limiting). Run it locally or behind your own auth.
