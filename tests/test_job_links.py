"""PRD #206 / #209: Job Link happy path — helpers, dashboard HTML route, open/close/boot sync."""

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from src.web.server import app

from kanban_js import read_dashboard_module, read_drawer_controller

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


# --- Pure Job Link path helpers ---


def test_parse_job_link_path_numeric_id():
    """`/jobs/{id}` parses to that numeric job id."""
    result = _run_node(
        """
        import { parseJobLinkPath } from './src/web/static/js/jobLinks.js';

        const r = parseJobLinkPath('/jobs/42');
        if (r.type !== 'job' || r.id !== 42) process.exit(1);
        if (parseJobLinkPath('/jobs/7').id !== 7) process.exit(2);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_parse_job_link_path_board_root():
    """`/`, `/dashboard`, and bare `/jobs` are board root (not a Job Link)."""
    result = _run_node(
        """
        import { parseJobLinkPath } from './src/web/static/js/jobLinks.js';

        for (const path of ['/', '/dashboard', '/jobs', '/jobs/']) {
          const r = parseJobLinkPath(path);
          if (r.type !== 'board') {
            console.error('expected board for', path, r);
            process.exit(1);
          }
        }
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_parse_job_link_path_rejects_non_numeric():
    """Non-numeric `/jobs/...` segments are invalid Job Links."""
    result = _run_node(
        """
        import { parseJobLinkPath } from './src/web/static/js/jobLinks.js';

        for (const path of ['/jobs/abc', '/jobs/12x', '/jobs/3.14', '/jobs/-1']) {
          const r = parseJobLinkPath(path);
          if (r.type !== 'invalid') {
            console.error('expected invalid for', path, r);
            process.exit(1);
          }
        }
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_build_job_link_path():
    """buildJobLinkPath maps a numeric id to `/jobs/{id}`."""
    result = _run_node(
        """
        import { buildJobLinkPath, BOARD_ROOT_PATH } from './src/web/static/js/jobLinks.js';

        if (buildJobLinkPath(42) !== '/jobs/42') process.exit(1);
        if (buildJobLinkPath(7) !== '/jobs/7') process.exit(2);
        if (BOARD_ROOT_PATH !== '/') process.exit(3);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


# --- HTTP seam: GET /jobs/{id} serves dashboard HTML ---


def test_get_jobs_id_serves_dashboard_html():
    """Hard navigation to a Job Link boots the same Kanban Dashboard HTML as `/`."""
    client = TestClient(app)
    root = client.get("/")
    assert root.status_code == 200
    job_link = client.get("/jobs/42")
    assert job_link.status_code == 200
    assert "text/html" in job_link.headers.get("content-type", "")
    assert job_link.text == root.text
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert dash.text == root.text


def test_job_link_route_does_not_shadow_api_or_static():
    """`/api/*` and `/static/*` stay available when Job Link routes exist."""
    client = TestClient(app)
    api = client.get("/api/health")
    assert api.status_code == 200
    css = client.get("/static/css/dashboard.css")
    assert css.status_code == 200
    assert ":root" in css.text
    js = client.get("/static/js/jobLinks.js")
    assert js.status_code == 200
    assert "export " in js.text


# --- Wiring: open / close / boot URL sync ---


def test_open_drawer_pushes_job_link():
    """Opening a job from the drawer pushes `/jobs/{id}` in browser history."""
    drawer = read_drawer_controller()
    assert "from './jobLinks.js'" in drawer or 'from "./jobLinks.js"' in drawer
    start = drawer.find("async function openJobDetailsDrawer(")
    assert start != -1
    body = drawer[start : start + 900]
    assert "pushJobLinkHistory" in body


def test_close_drawer_pushes_board_root():
    """Closing the drawer pushes board root `/` in browser history."""
    drawer = read_drawer_controller()
    start = drawer.find("function closeDrawerImmediate(")
    assert start != -1
    body = drawer[start : start + 400]
    assert "pushBoardRootHistory" in body


def test_dashboard_boot_opens_job_link_when_on_board():
    """After loadJobs, a valid Job Link path opens the drawer if the job is loaded."""
    app_js = read_dashboard_module("dashboardApp.js")
    assert "parseJobLinkPath" in app_js
    assert "findJob" in app_js
    # Boot runs after jobs load so the in-memory board set is ready.
    load_idx = app_js.find("board.loadJobs()")
    assert load_idx != -1
    after_load = app_js[load_idx : load_idx + 900]
    assert "parseJobLinkPath" in after_load
    assert "openJobDetailsDrawer" in after_load
    assert "findJob" in after_load
    assert ".then(" in after_load or ".finally(" in after_load


def test_push_helpers_update_history_when_path_changes():
    """pushJobLinkHistory / pushBoardRootHistory push only when the path differs."""
    result = _run_node(
        """
        import {
          pushJobLinkHistory,
          pushBoardRootHistory,
          BOARD_ROOT_PATH,
        } from './src/web/static/js/jobLinks.js';

        const pushes = [];
        globalThis.location = { pathname: '/' };
        globalThis.history = {
          pushState(state, _title, url) {
            pushes.push({ state, url });
            globalThis.location.pathname = url;
          },
        };

        pushJobLinkHistory(42);
        if (pushes.length !== 1 || pushes[0].url !== '/jobs/42') process.exit(1);
        pushJobLinkHistory(42);
        if (pushes.length !== 1) process.exit(2);

        pushBoardRootHistory();
        if (pushes.length !== 2 || pushes[1].url !== BOARD_ROOT_PATH) process.exit(3);
        pushBoardRootHistory();
        if (pushes.length !== 2) process.exit(4);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout
