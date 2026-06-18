"""Tracer tests: Kanban Dashboard modules expose behavior through focused submodules."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from src.web.server import app

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
JOB_STORE_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "jobStore.js")
BOARD_RENDERER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "boardRenderer.js")
DRAWER_CONTROLLER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "drawerController.js")
TASK_LOG_CLIENT_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "taskLogClient.js")
HTML_PATH = os.path.join(REPO_ROOT, "src", "web", "dashboard.html")


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_job_store_round_trips_jobs():
    """jobStore owns in-memory job list — set, find, update, remove."""
    result = _run_node(
        """
        import {
          getJobs, setJobs, findJob, updateJob, removeJob, addJob, hasJobMatching,
        } from './src/web/static/js/jobStore.js';

        setJobs([]);
        if (getJobs().length !== 0) process.exit(1);

        setJobs([{ id: 1, title: 'QA', company: 'Acme' }]);
        if (findJob(1)?.title !== 'QA') process.exit(2);

        updateJob(1, { id: 1, title: 'PM', company: 'Acme' });
        if (findJob(1)?.title !== 'PM') process.exit(3);

        addJob({ id: 2, title: 'SDET', company: 'Beta' });
        if (getJobs().length !== 2) process.exit(4);
        if (!hasJobMatching('SDET', 'Beta')) process.exit(5);

        removeJob(1);
        if (getJobs().length !== 1 || findJob(1)) process.exit(6);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_filters_and_sorts_jobs():
    """boardRenderer applies Board Controls filters without touching the DOM."""
    result = _run_node(
        """
        import { filterJobs, sortJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          { id: 1, remoteType: 'remote', size: '10-50', isRecruiter: false, matchScore: 70, date: '2026-06-01' },
          { id: 2, remoteType: 'hybrid', size: '1000+', isRecruiter: true, matchScore: 90, date: '2026-06-05' },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'remote',
          size: 'all',
          recruiter: 'exclude',
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(1);

        const sorted = sortJobs(filtered, 'match_desc');
        if (sorted[0].matchScore !== 70) process.exit(2);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_controller_substitutes_greeting_name():
    """drawerController applies Name Placeholder greeting substitution."""
    result = _run_node(
        """
        import {
          NAME_PLACEHOLDER,
          applyGreetingName,
          normalizeGreeting,
          contactGroup,
        } from './src/web/static/js/drawerController.js';

        const template = `Hello ${NAME_PLACEHOLDER},\\n\\nInterested in the role.`;
        const personalized = applyGreetingName(template, 'Jane');
        if (!personalized.startsWith('Hello Jane,')) process.exit(1);

        const restored = normalizeGreeting(personalized);
        if (!restored.includes(NAME_PLACEHOLDER)) process.exit(2);

        if (contactGroup({ is_recruiter: true }) !== 'recruiters') process.exit(3);
        if (contactGroup({ russian_speaker: true }) !== 'russian_speakers') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_controller_contact_sample_actions_after_empty_reclassify():
    """Load More / Re-classify stay available when enrichment ran but contacts are empty."""
    result = _run_node(
        """
        import { hasContactSampleActions } from './src/web/static/js/drawerController.js';

        const enrichedNoContacts = {
          status: 'accepted',
          recruiterOutreachTemplate: 'Hello ______,',
        };
        if (!hasContactSampleActions(enrichedNoContacts, [])) process.exit(1);

        const freshAccepted = { status: 'accepted' };
        if (hasContactSampleActions(freshAccepted, [])) process.exit(2);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_task_log_client_routes_sse_message_types():
    """taskLogClient routes log/result/done SSE payloads through one handler."""
    result = _run_node(
        """
        import { handleTaskLogMessage } from './src/web/static/js/taskLogClient.js';

        const logs = [];
        const results = [];
        let done = false;

        handleTaskLogMessage(
          { type: 'log', message: 'hello', level: 'info' },
          { addLogLine: (msg, level) => logs.push({ msg, level }), onResult: (d) => results.push(d), onDone: () => { done = true; } },
        );
        handleTaskLogMessage(
          { type: 'result', job: { id: 1 } },
          { addLogLine: () => {}, onResult: (d) => results.push(d), onDone: () => { done = true; } },
        );
        handleTaskLogMessage(
          { type: 'done' },
          { addLogLine: () => {}, onResult: () => {}, onDone: () => { done = true; } },
        );

        if (logs.length !== 1 || logs[0].msg !== 'hello') process.exit(1);
        if (results.length !== 1 || results[0].job?.id !== 1) process.exit(2);
        if (!done) process.exit(3);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_dashboard_has_no_inline_mock_job_database():
    """Kanban Dashboard loads jobs from the API — no static masterJobs mock array."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    for marker in ('<script type="module">', '<script>'):
        script_start = content.find(marker)
        if script_start != -1:
            break
    else:
        raise AssertionError("<script> block not found")
    script_end = content.rindex("</script>")
    script = content[script_start:script_end]
    assert "let masterJobs = [" not in script
    assert "Senior QA Automation Engineer" not in script
    assert "Using static fallback database" not in script


def test_dashboard_loads_kanban_modules():
    """dashboard.html imports Kanban Dashboard modules instead of inline monolith state."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    assert 'type="module"' in content
    assert "/static/js/jobStore.js" in content
    assert "/static/js/boardRenderer.js" in content
    assert "/static/js/drawerController.js" in content
    assert "/static/js/taskLogClient.js" in content


def test_server_serves_kanban_static_modules():
    """FastAPI serves extracted dashboard JS modules."""
    client = TestClient(app)
    for path in (
        "/static/js/jobStore.js",
        "/static/js/boardRenderer.js",
        "/static/js/drawerController.js",
        "/static/js/taskLogClient.js",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "export " in resp.text


def test_board_renderer_shows_enriching_badge_for_active_task():
    """boardRenderer.cardEnrichingBadge returns spinner for matching job, empty otherwise."""
    result = _run_node(
        """
        import { cardEnrichingBadge } from './src/web/static/js/boardRenderer.js';

        const badge = cardEnrichingBadge(42, 42);
        if (!badge.includes('fa-spinner')) process.exit(1);
        if (!badge.includes('Enriching')) process.exit(2);

        const noBadge = cardEnrichingBadge(1, 42);
        if (noBadge !== '') process.exit(3);

        const nullBadge = cardEnrichingBadge(1, null);
        if (nullBadge !== '') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_shows_load_more_badge_for_active_task():
    """boardRenderer.cardLoadMoreBadge returns spinner for matching job, empty otherwise."""
    result = _run_node(
        """
        import { cardLoadMoreBadge } from './src/web/static/js/boardRenderer.js';

        const badge = cardLoadMoreBadge(42, 42);
        if (!badge.includes('fa-spinner')) process.exit(1);
        if (!badge.includes('Loading contacts')) process.exit(2);

        const noBadge = cardLoadMoreBadge(1, 42);
        if (noBadge !== '') process.exit(3);

        const nullBadge = cardLoadMoreBadge(1, null);
        if (nullBadge !== '') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_shows_reclassify_badge_for_active_task():
    """boardRenderer.cardReclassifyBadge returns spinner for matching job, empty otherwise."""
    result = _run_node(
        """
        import { cardReclassifyBadge } from './src/web/static/js/boardRenderer.js';

        const badge = cardReclassifyBadge(42, [42, 7]);
        if (!badge.includes('fa-spinner')) process.exit(1);
        if (!badge.includes('Re-classifying')) process.exit(2);

        const noBadge = cardReclassifyBadge(1, [42, 7]);
        if (noBadge !== '') process.exit(3);

        const emptyBadge = cardReclassifyBadge(1, []);
        if (emptyBadge !== '') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_shows_reclassify_progress_banner():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "Re-classifying contacts" in content, \
        "drawerController must show in-drawer spinner while re-classifying"
    assert "refreshDrawerIfOpen" in content, \
        "drawerController must export refreshDrawerIfOpen to avoid reopening closed drawer"
