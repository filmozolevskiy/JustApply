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


def test_job_store_integrates_incoming_search_jobs():
    """integrateIncomingJobs adds new jobs and skips duplicates by id or title/company."""
    result = _run_node(
        """
        import {
          getJobs, setJobs, findJob, integrateIncomingJobs,
        } from './src/web/static/js/jobStore.js';

        setJobs([{ id: 1, title: 'QA', company: 'Acme', status: 'scraped' }]);

        const added = integrateIncomingJobs([
          { id: 1, title: 'QA', company: 'Acme', status: 'scraped' },
          { id: 2, title: 'PM', company: 'Beta', status: 'scraped' },
          { title: 'PM', company: 'Beta', status: 'scraped' },
        ]);
        if (added !== 1) process.exit(1);
        if (getJobs().length !== 2) process.exit(2);
        if (findJob(2)?.title !== 'PM') process.exit(3);

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


def test_board_renderer_search_filters_by_title_company_location_description():
    """Board Search uses multi-word AND across title, company, location, and description."""
    result = _run_node(
        """
        import {
          filterJobs,
          jobMatchesBoardSearch,
          parseBoardSearchTerms,
        } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'Senior QA Engineer',
            company: 'Acme Corp',
            location: 'Remote, US',
            description: 'Python and Selenium automation',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
          },
          {
            id: 2,
            title: 'Project Manager',
            company: 'Beta Inc',
            location: 'New York, Hybrid',
            description: 'Agile delivery leadership',
            remoteType: 'hybrid',
            size: '1000+',
            isRecruiter: false,
          },
        ];

        if (parseBoardSearchTerms('  QA   remote ').join(',') !== 'qa,remote') process.exit(1);
        if (!jobMatchesBoardSearch(jobs[0], 'qa remote')) process.exit(2);
        if (jobMatchesBoardSearch(jobs[1], 'qa remote')) process.exit(3);
        if (!jobMatchesBoardSearch(jobs[0], 'selenium')) process.exit(4);
        if (!jobMatchesBoardSearch(jobs[1], 'beta')) process.exit(5);
        if (!jobMatchesBoardSearch(jobs[0], '')) process.exit(6);

        const filtered = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'QA remote',
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(7);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_search_matches_contact_names():
    """Board Search includes contact display names in the haystack (name only, case-insensitive AND)."""
    result = _run_node(
        """
        import {
          filterJobs,
          jobMatchesBoardSearch,
          jobContactsMatchBoardSearch,
        } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'Backend Engineer',
            company: 'Acme Corp',
            location: 'Remote',
            description: 'API development',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            contacts: [
              { name: 'Jane Smith', title: 'Technical Recruiter', url: 'https://linkedin.com/in/jane' },
              { name: 'Bob Lee', title: 'Engineering Manager', url: 'https://linkedin.com/in/bob', contacted: true },
            ],
          },
          {
            id: 2,
            title: 'Project Manager',
            company: 'Beta Inc',
            location: 'New York',
            description: 'Agile delivery',
            remoteType: 'hybrid',
            size: '1000+',
            isRecruiter: false,
            contacts: [],
          },
        ];

        if (!jobMatchesBoardSearch(jobs[0], 'jane')) process.exit(1);
        if (jobMatchesBoardSearch(jobs[1], 'jane')) process.exit(2);
        if (!jobMatchesBoardSearch(jobs[0], 'JANE SMITH')) process.exit(3);
        if (jobMatchesBoardSearch(jobs[0], 'recruiter')) process.exit(4);
        if (!jobMatchesBoardSearch(jobs[0], 'jane engineer')) process.exit(5);
        if (jobMatchesBoardSearch(jobs[0], 'jane beta')) process.exit(6);
        if (!jobContactsMatchBoardSearch(jobs[0], 'jane smith')) process.exit(7);
        if (jobContactsMatchBoardSearch(jobs[0], 'engineer')) process.exit(8);
        if (jobContactsMatchBoardSearch(jobs[1], 'jane')) process.exit(9);
        if (!jobContactsMatchBoardSearch(jobs[0], '')) process.exit(10);

        const filtered = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'jane',
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(11);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_search_combines_with_other_board_filters():
    """Board Search ANDs with remote, size, and recruiter filters."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'QA Lead',
            company: 'Acme',
            location: 'Remote',
            description: 'Testing platform',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
          },
          {
            id: 2,
            title: 'QA Lead',
            company: 'Agency Staffing',
            location: 'Remote',
            description: 'Testing platform',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: true,
          },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'remote',
          size: 'all',
          recruiter: 'exclude',
          search: 'qa',
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(1);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_job_order_follows_lanes_and_sort():
    """getBoardJobOrder returns jobs lane-by-lane using the active sort."""
    result = _run_node(
        """
        import { getBoardJobOrder } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          { id: 1, status: 'scraped', matchScore: 60 },
          { id: 2, status: 'accepted', matchScore: 90 },
          { id: 3, status: 'scraped', matchScore: 80 },
          { id: 4, status: 'rejected', matchScore: 50 },
        ];

        const ordered = getBoardJobOrder(jobs, { sortBy: 'match_desc' });
        if (ordered.map((j) => j.id).join(',') !== '3,1,2,4') process.exit(1);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_dashboard_drawer_has_prev_next_navigation():
    """Job drawer exposes previous/next navigation controls."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    assert 'id="drawer-nav-prev"' in content
    assert 'id="drawer-nav-next"' in content
    assert "navigateDrawerJob" in content

    with open(DRAWER_CONTROLLER_PATH, encoding="utf-8") as f:
        drawer = f.read()
    assert "navigateDrawerJob" in drawer
    assert "getBoardJobOrder" in drawer


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


def test_drawer_controller_company_row_and_size_helpers():
    """Drawer company row shows LinkedIn badge only when companyUrl is present."""
    result = _run_node(
        """
        import { buildDrawerCompanyRowHtml } from './src/web/static/js/drawerController.js';

        const withUrl = buildDrawerCompanyRowHtml('Acme Corp', 'https://www.linkedin.com/company/acme/');
        if (!withUrl.includes('<strong>Acme Corp</strong>')) process.exit(1);
        if (!withUrl.includes('drawer-company-linkedin')) process.exit(2);
        if (!withUrl.includes('View Company on LinkedIn')) process.exit(3);

        const withoutUrl = buildDrawerCompanyRowHtml('Acme Corp', '');
        if (withoutUrl.includes('drawer-company-linkedin')) process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_controller_pick_default_active_contact_deprioritizes_elsewhere():
    """Active Contact defaults to uncontacted contacts without Contacted Elsewhere first."""
    result = _run_node(
        """
        import {
          pickDefaultActiveContact,
          hasContactedElsewhere,
        } from './src/web/static/js/drawerController.js';

        const contacts = [
          { name: 'A', contacted: false, contactedElsewhere: { jobId: 9, company: 'X', title: 'Y' } },
          { name: 'B', contacted: false },
          { name: 'C', contacted: true },
        ];
        if (pickDefaultActiveContact(contacts) !== 1) process.exit(1);
        if (!hasContactedElsewhere(contacts[0])) process.exit(2);

        const allElsewhere = [
          { name: 'A', contacted: false, contactedElsewhere: { jobId: 9, company: 'X', title: 'Y' } },
          { name: 'B', contacted: false, contactedElsewhere: { jobId: 10, company: 'Z', title: 'W' } },
        ];
        if (pickDefaultActiveContact(allElsewhere) !== 0) process.exit(3);

        const allContacted = [{ name: 'C', contacted: true }];
        if (pickDefaultActiveContact(allContacted) !== 0) process.exit(4);

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


def test_dashboard_has_summary_log_level_style():
    """Task Logs summary level has distinct styling in dashboard CSS."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    assert ".terminal-text.summary" in content
    assert "border-top" in content


def test_board_renderer_includes_unclassified_badge():
    """boardRenderer shows Unclassified badge with hover tooltip for unclassified jobs."""
    with open(BOARD_RENDERER_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "job.unclassified" in content
    assert "Unclassified" in content
    assert "title=" in content


def test_drawer_shows_reclassify_progress_banner():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "Re-classifying contacts" in content, \
        "drawerController must show in-drawer spinner while re-classifying"
    assert "refreshDrawerIfOpen" in content, \
        "drawerController must export refreshDrawerIfOpen to avoid reopening closed drawer"


def test_drawer_inline_handlers_exported_to_window():
    """Inline oninput/onclick in drawer HTML require globals on window."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    window_block = content[content.find("Object.assign(window,") : content.find("});", content.find("Object.assign(window,")) + 3]
    for name in (
        "postJobComment",
        "cancelJobComment",
        "postOutreachTemplate",
        "cancelOutreachTemplate",
        "onCommentDraftInput",
        "onOutreachDraftInput",
        "updateOutreachCounter",
    ):
        assert f"{name}," in window_block, f"{name} must be exported to window for drawer inline handlers"
