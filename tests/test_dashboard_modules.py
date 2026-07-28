"""Tracer tests: Kanban Dashboard modules expose behavior through focused submodules."""

import os
import subprocess

from fastapi.testclient import TestClient
from src.web.server import app
from tests.kanban_js import DASHBOARD_CSS_PATH, load_dashboard_js, read_dashboard_css

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

def test_board_renderer_resolve_jobs_archived_fetch_param():
    """Active visibility + non-empty search or favorites-only fetches all jobs; otherwise unchanged."""
    result = _run_node(
        """
        import { resolveJobsArchivedFetchParam } from './src/web/static/js/boardRenderer.js';

        if (resolveJobsArchivedFetchParam('active', 'jane') !== 'all') process.exit(1);
        if (resolveJobsArchivedFetchParam('active', '  ') !== 'active') process.exit(2);
        if (resolveJobsArchivedFetchParam('active', '') !== 'active') process.exit(3);
        if (resolveJobsArchivedFetchParam('archived', 'jane') !== 'archived') process.exit(4);
        if (resolveJobsArchivedFetchParam('all', 'jane') !== 'all') process.exit(5);
        if (resolveJobsArchivedFetchParam('active', '', true) !== 'all') process.exit(6);
        if (resolveJobsArchivedFetchParam('active', '', false) !== 'active') process.exit(7);
        if (resolveJobsArchivedFetchParam('archived', '', true) !== 'archived') process.exit(8);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_board_renderer_active_search_surfaces_archived_on_contact_match_only():
    """Under Active visibility, archived jobs appear only when contact names match search."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const base = {
          remoteType: 'remote',
          size: '10-50',
          isRecruiter: false,
          status: 'rejected',
        };

        const jobs = [
          {
            id: 1,
            title: 'Active QA',
            company: 'Acme',
            location: 'Remote',
            description: 'Testing',
            archived: false,
            contacts: [{ name: 'Jane Smith' }],
            ...base,
          },
          {
            id: 2,
            title: 'Old Role',
            company: 'Hidden Corp',
            location: 'Remote',
            description: 'Legacy',
            archived: true,
            contacts: [{ name: 'Jane Smith' }],
            ...base,
          },
          {
            id: 3,
            title: 'Hidden Corp PM',
            company: 'Hidden Corp',
            location: 'Remote',
            description: 'Legacy',
            archived: true,
            contacts: [],
            ...base,
          },
        ];

        const activeSearchFilters = {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'jane',
          archivedVisibility: 'active',
        };

        const filtered = filterJobs(jobs, activeSearchFilters);
        const ids = filtered.map((j) => j.id).sort((a, b) => a - b);
        if (ids.join(',') !== '1,2') process.exit(1);

        const companyOnly = filterJobs(jobs, {
          ...activeSearchFilters,
          search: 'hidden',
        });
        if (companyOnly.some((j) => j.archived)) process.exit(2);

        const noSearch = filterJobs(jobs, {
          ...activeSearchFilters,
          search: '',
        });
        if (noSearch.some((j) => j.archived)) process.exit(3);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_board_renderer_archived_and_all_visibility_skip_contact_bypass():
    """Archived and All visibility modes use normal search — no contact-only bypass."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const job = {
          id: 9,
          title: 'Hidden Corp Role',
          company: 'Hidden Corp',
          location: 'Remote',
          description: 'Legacy',
          remoteType: 'remote',
          size: '10-50',
          isRecruiter: false,
          status: 'rejected',
          archived: true,
          contacts: [],
        };

        const archivedMode = filterJobs([job], {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'hidden',
          archivedVisibility: 'archived',
        });
        if (archivedMode.length !== 1) process.exit(1);

        const allMode = filterJobs([job], {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'hidden',
          archivedVisibility: 'all',
        });
        if (allMode.length !== 1) process.exit(2);

        const activeMode = filterJobs([job], {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'hidden',
          archivedVisibility: 'active',
        });
        if (activeMode.length !== 0) process.exit(3);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_board_renderer_active_archived_bypass_combines_with_other_filters():
    """Contact-name archived bypass still respects remote, size, and recruiter filters."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'Role A',
            company: 'Acme',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            archived: true,
            contacts: [{ name: 'Jane Smith' }],
          },
          {
            id: 2,
            title: 'Role B',
            company: 'Agency',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: true,
            archived: true,
            contacts: [{ name: 'Jane Smith' }],
          },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'remote',
          size: 'all',
          recruiter: 'exclude',
          search: 'jane',
          archivedVisibility: 'active',
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(1);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_dashboard_load_jobs_uses_archived_fetch_resolver():
    """loadJobs uses resolveJobsArchivedFetchParam for search-aware fetch under Active."""
    content = load_dashboard_js()
    assert "resolveJobsArchivedFetchParam" in content
    assert "getJobsFetchArchivedParam" in content

def test_dashboard_clear_board_search_reloads_jobs():
    """Clearing Board Search reloads jobs so archived rows drop under Active visibility."""
    content = load_dashboard_js()
    clear_fn = content[content.find("function clearBoardSearch"): content.find("function resetBoardControls")]
    assert "loadJobs()" in clear_fn

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

def test_board_renderer_favorites_only_shows_favorited_jobs():
    """Favorites Filter keeps only jobs with favorited === true."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'QA Lead',
            company: 'Acme',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            favorited: true,
          },
          {
            id: 2,
            title: 'SDET',
            company: 'Beta',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            favorited: false,
          },
        ];

        const off = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          favoritesOnly: false,
        });
        if (off.map((j) => j.id).join(',') !== '1,2') process.exit(1);

        const on = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          favoritesOnly: true,
        });
        if (on.length !== 1 || on[0].id !== 1) process.exit(2);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_board_renderer_favorites_only_ands_with_search_and_remote():
    """Favorites Filter ANDs with Board Search and remote type filters."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1,
            title: 'QA Lead',
            company: 'Acme',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            favorited: true,
          },
          {
            id: 2,
            title: 'QA Lead',
            company: 'Beta',
            location: 'Hybrid',
            description: 'Testing',
            remoteType: 'hybrid',
            size: '10-50',
            isRecruiter: false,
            favorited: true,
          },
          {
            id: 3,
            title: 'QA Lead',
            company: 'Gamma',
            location: 'Remote',
            description: 'Testing',
            remoteType: 'remote',
            size: '10-50',
            isRecruiter: false,
            favorited: false,
          },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'remote',
          size: 'all',
          recruiter: 'all',
          search: 'qa',
          favoritesOnly: true,
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(1);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_board_renderer_favorites_only_surfaces_favorited_archived_under_active():
    """Under Active visibility, favorites-only includes favorited archived jobs."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const base = {
          title: 'Old QA',
          company: 'Acme',
          location: 'Remote',
          description: 'Testing',
          remoteType: 'remote',
          size: '10-50',
          isRecruiter: false,
          status: 'rejected',
        };

        const jobs = [
          { id: 1, ...base, archived: false, favorited: true },
          { id: 2, ...base, archived: true, favorited: true },
          { id: 3, ...base, archived: true, favorited: false },
          { id: 4, ...base, archived: false, favorited: false },
        ];

        const favoritesOn = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: '',
          archivedVisibility: 'active',
          favoritesOnly: true,
        });
        const onIds = favoritesOn.map((j) => j.id).sort((a, b) => a - b);
        if (onIds.join(',') !== '1,2') process.exit(1);

        const favoritesOff = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: '',
          archivedVisibility: 'active',
          favoritesOnly: false,
        });
        if (favoritesOff.some((j) => j.archived)) process.exit(2);
        if (favoritesOff.map((j) => j.id).sort((a, b) => a - b).join(',') !== '1,4') process.exit(3);

        const withSearch = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          search: 'acme',
          archivedVisibility: 'active',
          favoritesOnly: true,
        });
        if (withSearch.map((j) => j.id).sort((a, b) => a - b).join(',') !== '1,2') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_employment_type_none_checked_passes_all_including_unknown():
    """Empty Employment Type refine leaves all types and unknowns visible."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          { id: 1, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: 'Full-time' },
          { id: 2, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: 'Contract' },
          { id: 3, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: '' },
          { id: 4, remoteType: 'remote', size: '10-50', isRecruiter: false },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          employmentTypes: [],
        });
        if (filtered.map((j) => j.id).join(',') !== '1,2,3,4') process.exit(1);

        const omitted = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
        });
        if (omitted.map((j) => j.id).join(',') !== '1,2,3,4') process.exit(2);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_employment_type_refine_keeps_selected_hides_unknown():
    """Active Employment Type refine keeps matching types and hides unknowns."""
    result = _run_node(
        """
        import { filterJobs } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          { id: 1, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: 'Full-time' },
          { id: 2, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: 'Contract' },
          { id: 3, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: 'Part-time' },
          { id: 4, remoteType: 'remote', size: '10-50', isRecruiter: false, employmentType: '' },
          { id: 5, remoteType: 'remote', size: '10-50', isRecruiter: false },
        ];

        const contractOnly = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          employmentTypes: ['Contract'],
        });
        if (contractOnly.length !== 1 || contractOnly[0].id !== 2) process.exit(1);

        const multi = filterJobs(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          employmentTypes: ['Full-time', 'Contract'],
        });
        if (multi.map((j) => j.id).join(',') !== '1,2') process.exit(2);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_employment_type_ands_with_search_remote_favorites():
    """Employment Type refine ANDs with search, remote, and favorites filters."""
    result = _run_node(
        """
        import { filterJobs, getBoardJobOrder } from './src/web/static/js/boardRenderer.js';

        const jobs = [
          {
            id: 1, status: 'matched', title: 'QA Lead', company: 'Acme',
            location: 'Remote', description: 'Testing', remoteType: 'remote',
            size: '10-50', isRecruiter: false, favorited: true,
            employmentType: 'Contract', matchScore: 80,
          },
          {
            id: 2, status: 'matched', title: 'QA Lead', company: 'Beta',
            location: 'Hybrid', description: 'Testing', remoteType: 'hybrid',
            size: '10-50', isRecruiter: false, favorited: true,
            employmentType: 'Contract', matchScore: 90,
          },
          {
            id: 3, status: 'matched', title: 'QA Lead', company: 'Gamma',
            location: 'Remote', description: 'Testing', remoteType: 'remote',
            size: '10-50', isRecruiter: false, favorited: true,
            employmentType: 'Full-time', matchScore: 95,
          },
          {
            id: 4, status: 'matched', title: 'QA Lead', company: 'Delta',
            location: 'Remote', description: 'Testing', remoteType: 'remote',
            size: '10-50', isRecruiter: false, favorited: false,
            employmentType: 'Contract', matchScore: 70,
          },
        ];

        const filtered = filterJobs(jobs, {
          remote: 'remote',
          size: 'all',
          recruiter: 'all',
          search: 'qa',
          favoritesOnly: true,
          employmentTypes: ['Contract'],
        });
        if (filtered.length !== 1 || filtered[0].id !== 1) process.exit(1);

        const ordered = getBoardJobOrder(jobs, {
          remote: 'all',
          size: 'all',
          recruiter: 'all',
          sortBy: 'match_desc',
          employmentTypes: ['Contract'],
        });
        if (ordered.map((j) => j.id).join(',') !== '2,1,4') process.exit(2);

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
    dashboard_js = load_dashboard_js()
    assert "navigateDrawerJob" in dashboard_js

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


def test_task_log_client_batch_poller_sse_uses_single_event_source():
    """Batch-poller SSE reuses handleTaskLogMessage and replaces prior EventSource."""
    result = _run_node(
        """
        import {
          BATCH_POLLER_LOG_SKIP_KEY,
          createTaskLogClient,
        } from './src/web/static/js/taskLogClient.js';

        const store = new Map();
        globalThis.localStorage = {
          getItem: (k) => (store.has(k) ? store.get(k) : null),
          setItem: (k, v) => store.set(k, String(v)),
          removeItem: (k) => store.delete(k),
        };
        globalThis.document = {
          getElementById: () => null,
        };
        globalThis.window = {
          clearTimeout: clearTimeout,
          setTimeout: setTimeout,
        };

        const constructed = [];
        class FakeEventSource {
          constructor(url) {
            this.url = url;
            this.closed = false;
            this.onmessage = null;
            this.onerror = null;
            constructed.push(this);
          }
          close() {
            this.closed = true;
          }
        }
        globalThis.EventSource = FakeEventSource;

        const client = createTaskLogClient();
        store.set(BATCH_POLLER_LOG_SKIP_KEY, '2');
        const first = client.connectBatchPollerLogStream();
        if (constructed.length !== 1) process.exit(1);
        if (!first.url.includes('/api/batch-poller/logs?skip=2')) process.exit(2);
        if (client.getBatchPollerEventSource() !== first) process.exit(3);

        const second = client.connectBatchPollerLogStream();
        if (constructed.length !== 2) process.exit(4);
        if (!first.closed || first._intentionalClose !== true) process.exit(5);
        if (client.getBatchPollerEventSource() !== second) process.exit(6);
        if (second.url.includes('/api/logs/')) process.exit(7);

        second.onmessage({
          data: JSON.stringify({
            type: 'log',
            level: 'summary',
            message: 'Batch chunk completed: 1 matched, 0 attribute-filtered, 0 fallback-rejected, 0 failed, 0 unclassified',
          }),
        });
        if (store.get(BATCH_POLLER_LOG_SKIP_KEY) !== '3') process.exit(8);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout

def test_dashboard_has_no_inline_mock_job_database():
    """Kanban Dashboard loads jobs from the API — no static masterJobs mock array."""
    content = load_dashboard_js()
    assert "let masterJobs = [" not in content
    assert "Senior QA Automation Engineer" not in content
    assert "Using static fallback database" not in content

def test_dashboard_loads_kanban_modules():
    """dashboard.html imports Kanban Dashboard modules instead of inline monolith state."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    assert 'type="module"' in content
    assert "/static/js/dashboardApp.js" in content
    dashboard_js = load_dashboard_js()
    assert "/static/js/jobStore.js" in dashboard_js or "from './jobStore.js'" in dashboard_js
    assert "/static/js/boardRenderer.js" in dashboard_js or "from './boardRenderer.js'" in dashboard_js
    assert "/static/js/drawerController.js" in dashboard_js or "from './drawerController.js'" in dashboard_js
    assert "/static/js/taskLogClient.js" in dashboard_js or "from './taskLogClient.js'" in dashboard_js
    assert "boardOrchestration.js" in dashboard_js
    assert "jobSearchSettings.js" in dashboard_js
    assert "spendConfirmation.js" in dashboard_js
    assert "evaluationLock.js" in dashboard_js
    assert "profileManager.js" in dashboard_js

def test_dashboard_links_stylesheet():
    """dashboard.html links extracted CSS from the static mount."""
    with open(HTML_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "/static/css/dashboard.css" in content
    assert "<style" not in content

def test_server_serves_dashboard_stylesheet():
    """FastAPI serves extracted dashboard CSS."""
    client = TestClient(app)
    resp = client.get("/static/css/dashboard.css")
    assert resp.status_code == 200
    assert ":root {" in resp.text
    assert ".kanban-board-container" in resp.text

def test_server_serves_kanban_static_modules():
    """FastAPI serves extracted dashboard JS modules."""
    client = TestClient(app)
    for path in (
        "/static/js/jobStore.js",
        "/static/js/boardRenderer.js",
        "/static/js/drawerController.js",
        "/static/js/taskLogClient.js",
        "/static/js/boardOrchestration.js",
        "/static/js/jobSearchSettings.js",
        "/static/js/spendConfirmation.js",
        "/static/js/evaluationLock.js",
        "/static/js/profileManager.js",
        "/static/js/dashboardApp.js",
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
    content = read_dashboard_css()
    assert ".terminal-text.summary" in content
    assert "border-top" in content
    assert os.path.isfile(DASHBOARD_CSS_PATH)

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
    content = load_dashboard_js()
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


def test_card_comment_root_count_chip_counts_roots_only():
    """Kanban card chip shows root Job Comment count; zero roots → no chrome; never body text."""
    result = _run_node(
        """
        import { cardCommentRootCountChip } from './src/web/static/js/boardRenderer.js';

        const empty = cardCommentRootCountChip({ comments: [] });
        if (empty !== '') process.exit(1);

        const missing = cardCommentRootCountChip({});
        if (missing !== '') process.exit(2);

        const oneRoot = cardCommentRootCountChip({
          comments: [
            { id: 'c1', parentId: null, body: 'Secret note body', createdAt: '2026-07-01T10:00:00Z' },
          ],
        });
        if (!oneRoot.includes('comment-root-count-chip')) process.exit(3);
        if (!oneRoot.includes('>1<') && !oneRoot.includes('> 1<') && !/\\b1\\b/.test(oneRoot)) process.exit(4);
        if (oneRoot.includes('Secret note body')) process.exit(5);

        const rootsAndReply = cardCommentRootCountChip({
          comments: [
            { id: 'r1', parentId: null, body: 'Root A', createdAt: '2026-07-01T10:00:00Z' },
            { id: 'r2', parentId: null, body: 'Root B', createdAt: '2026-07-02T10:00:00Z' },
            { id: 'reply', parentId: 'r1', body: 'Nested reply', createdAt: '2026-07-03T10:00:00Z' },
          ],
        });
        if (!/\\b2\\b/.test(rootsAndReply)) process.exit(6);
        if (rootsAndReply.includes('Root A') || rootsAndReply.includes('Nested reply')) process.exit(7);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_card_uses_comment_root_count_chip_not_text_preview():
    """Card header shows root-count chip; no italic comment body preview on the card."""
    with open(BOARD_RENDERER_PATH, encoding="utf-8") as f:
        board = f.read()
    css = read_dashboard_css()
    from kanban_js import read_drawer_controller

    drawer = read_drawer_controller()

    assert "cardCommentRootCountChip(job)" in board
    assert "comment-root-count-chip" in board
    assert "${commentChip}" in board
    assert "kanban-card-header-actions" in board
    # No legacy string-blob field or body text preview on the card.
    assert "job.comment " not in board
    assert "job.comment}" not in board
    assert "job.comment." not in board
    assert "fa-comment-dots" in board
    assert ".comment-root-count-chip" in css
    # Chip helper must not interpolate comment bodies onto the card.
    helper_start = board.find("function cardCommentRootCountChip")
    assert helper_start != -1
    helper_end = board.find("\nexport function", helper_start + 1)
    helper = board[helper_start:helper_end if helper_end != -1 else helper_start + 600]
    assert "body" not in helper or ".body" not in helper
    assert "c.body" not in helper
    assert "${" not in helper or "rootCount" in helper
    # Posting a root refreshes the board so the chip count updates without full page reload.
    post_start = drawer.find("function postJobComment(")
    assert post_start != -1
    post_body = drawer[post_start : post_start + 1600]
    assert "onJobMutated()" in post_body
    assert "job.comments" in post_body
