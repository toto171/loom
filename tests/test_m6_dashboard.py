"""M6 web dashboard: pages render, the static-check partial works, a composed run
goes end-to-end (compose -> gate -> sim -> assurance), and the dashboard inherits
the safety-line gate (a below-line swap is refused with 409 until re-validated)."""
import shutil
import warnings

warnings.simplefilter("ignore")  # starlette/httpx testclient deprecation noise

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.app import app  # noqa: E402
from loom.paths import locks_dir, runs_dir  # noqa: E402

client = TestClient(app)


def _cleanup(name: str) -> None:
    for d in runs_dir().glob(f"*{name}"):
        shutil.rmtree(d, ignore_errors=True)
    for p in [locks_dir() / f"{name}.lock.json", runs_dir() / ".composed" / f"{name}.yaml"]:
        p.unlink(missing_ok=True)


def _compose_form(name, **overrides):
    form = {
        "vehicle_name": name, "vehicle_class": "M1", "plant": "longitudinal",
        "scenario": "urban_drive", "impl_bms": "default", "impl_powertrain": "default",
        "impl_adas": "adas_stub", "impl_hmi": "default", "impl_body": "default",
    }
    form.update(overrides)
    return form


def test_pages_render():
    for path in ["/", "/compose", "/runs"]:
        assert client.get(path).status_code == 200


def test_check_partial_runs_the_static_checker():
    r = client.get("/check?spec=vehicle.example.yaml")
    assert r.status_code == 200
    assert "producer_uniqueness" in r.text and "Result: OK" in r.text


def test_composed_run_end_to_end_produces_assurance():
    name = "dash-pytest-ev"
    try:
        r = client.post("/run/compose", data=_compose_form(name), follow_redirects=False)
        assert r.status_code == 303
        run_id = r.headers["location"].split("/")[-1]
        detail = client.get(f"/runs/{run_id}")
        assert detail.status_code == 200
        assert 'class="mermaid"' in detail.text  # GSN rendered
        assert "components" in detail.text        # SBOM surfaced
    finally:
        _cleanup(name)


def test_check_rejects_path_traversal():
    # A crafted spec param must not read files outside spec/.
    for bad in ["../README.md", "../scenarios/urban_drive.yaml", "../pyproject.toml"]:
        r = client.get("/check", params={"spec": bad})
        assert r.status_code == 200
        assert "invalid spec path" in r.text


def test_composed_vehicle_name_is_sanitized_no_path_escape():
    from loom.paths import repo_root
    # a path-injection name must be neutralized to a safe lock/run-dir name.
    r = client.post("/run/compose", data=_compose_form("ignored", vehicle_name="../../pwned-test"),
                    follow_redirects=False)
    try:
        assert r.status_code == 303  # sanitized name -> valid -> ran
        assert (locks_dir() / "pwned-test.lock.json").exists()      # landed safely under locks/
        assert not (repo_root().parent / "pwned-test.lock.json").exists()  # did NOT escape
    finally:
        _cleanup("pwned-test")


def test_load_run_rejects_traversal():
    from loom.catalog import load_run
    assert load_run("../../etc") is None
    assert load_run("..") is None


def test_dashboard_inherits_safety_line_gate():
    name = "dash-gate-ev"
    try:
        # 1) establish a baseline (bms.default)
        assert client.post("/run/compose", data=_compose_form(name),
                           follow_redirects=False).status_code == 303
        # 2) below-line swap to custom_x without re-validation -> refused (409)
        refused = client.post("/run/compose", data=_compose_form(name, impl_bms="custom_x"),
                              follow_redirects=False)
        assert refused.status_code == 409
        assert "gate refused" in refused.text.lower()
        # 3) with --revalidate -> proceeds
        ok = client.post("/run/compose", data=_compose_form(name, impl_bms="custom_x", revalidate="true"),
                         follow_redirects=False)
        assert ok.status_code == 303
    finally:
        _cleanup(name)
