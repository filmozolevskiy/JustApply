/** Board orchestration — filters, rendering glue, DnD, and job actions. */

import {
  findJob, getJobs, integrateIncomingJobs, removeJob, setJobs, updateJob,
} from './jobStore.js';
import {
  filterJobs, getBoardFiltersFromDom, parseBoardSearchTerms, renderBoard,
  resolveJobsArchivedFetchParam,
} from './boardRenderer.js';
import {
  buildApifySpendBodyHtml,
  buildGlassdoorSpendBodyHtml,
  showSpendAckModal,
  showSpendConfirmModal,
} from './spendConfirmation.js';
import {
  ACTIVE_ENRICH_LOG_SKIP_KEY,
  ACTIVE_ENRICH_TASK_KEY,
  ACTIVE_COMPANY_RESEARCH_LOG_SKIP_KEY,
  ACTIVE_COMPANY_RESEARCH_TASK_KEY,
  ACTIVE_RECLASSIFY_TASKS_KEY,
  ACTIVE_SCRAPE_LOG_SKIP_KEY,
  ACTIVE_SCRAPE_TASK_KEY,
  loadReclassifyTaskMap,
  reclassifyTaskLogSkipKey,
  removeReclassifyTaskEntry,
  saveReclassifyTaskEntry,
} from './taskLogClient.js';

export function createBoardOrchestrator({
  addLogLine,
  clearLogs,
  closeTaskLogStreamQuietly,
  confirmDiscardUnsavedEdits,
  connectTaskLogStream,
  createDrawerController,
  expandLogsConsole,
  resetScrapeButtons,
  taskLog,
}) {
  let activeEnrichJobId = null;
  let activeLoadMoreJobId = null;
  let activeCompanyResearchJobId = null;
  let activeReclassifyJobIds = [];
  let boardSearchDebounceTimer = null;
  let lastJobsFetchArchivedParam = null;
  const BOARD_SEARCH_DEBOUNCE_MS = 300;
  const BOARD_CONTROLS_DEFAULTS = {
    search: '',
    remote: 'all',
    size: 'all',
    recruiter: 'exclude',
    sortBy: 'match_desc',
    archived: 'active',
  };

  function startPollingEnrichingJobs() {
    // Enrichment no longer changes lane status (stays Accepted) — no polling needed.
  }

  function getActiveBoardFilters() {
    return {
      ...getBoardFiltersFromDom(),
      enrichingJobId: activeEnrichJobId,
      loadMoreJobId: activeLoadMoreJobId,
      companyResearchJobId: activeCompanyResearchJobId,
      reclassifyJobIds: activeReclassifyJobIds,
    };
  }

  function getJobsFetchArchivedParam() {
    const archivedFilter = getArchivedFilter();
    const searchQuery = document.getElementById('board-filter-search')?.value || '';
    return resolveJobsArchivedFetchParam(archivedFilter, searchQuery);
  }

  function updateBoardSearchClearVisibility() {
    const input = document.getElementById('board-filter-search');
    const btn = document.getElementById('board-filter-search-clear');
    if (!input || !btn) return;
    btn.hidden = !input.value;
  }

  function updateBoardSearchEmptyHint(jobs, filters) {
    const hint = document.getElementById('board-search-empty-hint');
    if (!hint) return;
    const hasSearch = parseBoardSearchTerms(filters.search || '').length > 0;
    const filteredCount = filterJobs(jobs, filters).length;
    hint.hidden = !(hasSearch && filteredCount === 0);
  }

  function persistBoardSearch() {
    const value = document.getElementById('board-filter-search')?.value || '';
    localStorage.setItem('boardFilterSearch', value);
  }

  function onBoardSearchInput() {
    updateBoardSearchClearVisibility();
    if (boardSearchDebounceTimer) {
      clearTimeout(boardSearchDebounceTimer);
    }
    boardSearchDebounceTimer = setTimeout(() => {
      boardSearchDebounceTimer = null;
      persistBoardSearch();
      const fetchParam = getJobsFetchArchivedParam();
      if (fetchParam !== lastJobsFetchArchivedParam) {
        loadJobs().then(() => updateDrawerNav());
      } else {
        renderActiveVariant();
        updateDrawerNav();
      }
    }, BOARD_SEARCH_DEBOUNCE_MS);
  }

  function clearBoardSearch() {
    const input = document.getElementById('board-filter-search');
    if (input) {
      input.value = '';
    }
    if (boardSearchDebounceTimer) {
      clearTimeout(boardSearchDebounceTimer);
      boardSearchDebounceTimer = null;
    }
    persistBoardSearch();
    const fetchParam = getJobsFetchArchivedParam();
    if (fetchParam !== lastJobsFetchArchivedParam) {
      loadJobs().then(() => updateDrawerNav());
    } else {
      renderActiveVariant();
      updateDrawerNav();
    }
    updateBoardSearchClearVisibility();
  }

  function resetBoardControls() {
    const previousArchived = getArchivedFilter();

    if (boardSearchDebounceTimer) {
      clearTimeout(boardSearchDebounceTimer);
      boardSearchDebounceTimer = null;
    }

    const searchEl = document.getElementById('board-filter-search');
    const remoteEl = document.getElementById('board-filter-remote');
    const sizeEl = document.getElementById('board-filter-size');
    const recruiterEl = document.getElementById('board-filter-recruiter');
    const sortEl = document.getElementById('board-sort-by');
    const archivedEl = document.getElementById('board-filter-archived');

    if (searchEl) searchEl.value = BOARD_CONTROLS_DEFAULTS.search;
    if (remoteEl) remoteEl.value = BOARD_CONTROLS_DEFAULTS.remote;
    if (sizeEl) sizeEl.value = BOARD_CONTROLS_DEFAULTS.size;
    if (recruiterEl) recruiterEl.value = BOARD_CONTROLS_DEFAULTS.recruiter;
    if (sortEl) sortEl.value = BOARD_CONTROLS_DEFAULTS.sortBy;
    if (archivedEl) archivedEl.value = BOARD_CONTROLS_DEFAULTS.archived;

    localStorage.setItem('boardFilterSearch', BOARD_CONTROLS_DEFAULTS.search);
    localStorage.setItem('boardFilterRemote', BOARD_CONTROLS_DEFAULTS.remote);
    localStorage.setItem('boardFilterSize', BOARD_CONTROLS_DEFAULTS.size);
    localStorage.setItem('boardFilterRecruiter', BOARD_CONTROLS_DEFAULTS.recruiter);
    localStorage.setItem('boardSortBy', BOARD_CONTROLS_DEFAULTS.sortBy);
    localStorage.setItem('boardFilterArchived', BOARD_CONTROLS_DEFAULTS.archived);

    updateBoardSearchClearVisibility();

    if (previousArchived !== BOARD_CONTROLS_DEFAULTS.archived) {
      loadJobs().then(() => updateDrawerNav());
    } else {
      renderActiveVariant();
      updateDrawerNav();
    }
  }

  function renderActiveVariant() {
    const filters = getActiveBoardFilters();
    renderBoard(getJobs(), filters);
    updateBoardSearchEmptyHint(getJobs(), filters);
  }

  function integrateSearchResultFromStream(logData) {
    const incoming = [];
    if (logData.job) {
      incoming.push(logData.job);
    }
    if (logData.jobs?.length) {
      incoming.push(...logData.jobs);
    }
    const added = integrateIncomingJobs(incoming);
    if (added > 0) {
      renderActiveVariant();
    }
    return added;
  }

  const drawer = createDrawerController({
    onJobMutated: renderActiveVariant,
    addLogLine,
    confirmDiscardUnsavedEdits,
    getActiveReclassifyJobIds: () => activeReclassifyJobIds,
    getActiveLoadMoreJobId: () => activeLoadMoreJobId,
    getActiveCompanyResearchJobId: () => activeCompanyResearchJobId,
    getBoardFilters: getBoardFiltersFromDom,
  });
  const {
    cancelJobComment,
    cancelOutreachTemplate,
    closeDrawer,
    closeDrawerImmediate,
    copyDrawerOutreach,
    enrichJobFromDrawer,
    markAppliedFromDrawer,
    navigateDrawerJob,
    onCommentDraftInput,
    onOutreachDraftInput,
    openContactedElsewhereJob,
    openJobDetailsDrawer,
    postJobComment,
    postOutreachTemplate,
    refreshDrawerIfOpen,
    rejectJobFromDrawer,
    selectActiveContact,
    toggleActivityLog,
    toggleContacted,
    updateDrawerNav,
    updateOutreachCounter,
  } = drawer;

  function updateBoardFiltersAndSort() {
    const remoteFilter = document.getElementById('board-filter-remote')?.value || 'all';
    const sizeFilter = document.getElementById('board-filter-size')?.value || 'all';
    const recruiterFilter = document.getElementById('board-filter-recruiter')?.value || 'all';
    const sortBy = document.getElementById('board-sort-by')?.value || 'match_desc';

    localStorage.setItem('boardFilterRemote', remoteFilter);
    localStorage.setItem('boardFilterSize', sizeFilter);
    localStorage.setItem('boardFilterRecruiter', recruiterFilter);
    localStorage.setItem('boardSortBy', sortBy);

    renderActiveVariant();
    updateDrawerNav();
  }

  function getArchivedFilter() {
    return document.getElementById('board-filter-archived')?.value || localStorage.getItem('boardFilterArchived') || 'active';
  }

  function initBoardControls() {
    const remoteFilter = localStorage.getItem('boardFilterRemote') || BOARD_CONTROLS_DEFAULTS.remote;
    const sizeFilter = localStorage.getItem('boardFilterSize') || BOARD_CONTROLS_DEFAULTS.size;
    const recruiterFilter = localStorage.getItem('boardFilterRecruiter') || BOARD_CONTROLS_DEFAULTS.recruiter;
    const sortBy = localStorage.getItem('boardSortBy') || BOARD_CONTROLS_DEFAULTS.sortBy;
    const archivedFilter = localStorage.getItem('boardFilterArchived') || BOARD_CONTROLS_DEFAULTS.archived;

    const remoteEl = document.getElementById('board-filter-remote');
    const sizeEl = document.getElementById('board-filter-size');
    const recruiterEl = document.getElementById('board-filter-recruiter');
    const sortEl = document.getElementById('board-sort-by');
    const archivedEl = document.getElementById('board-filter-archived');

    const searchFilter = localStorage.getItem('boardFilterSearch') || BOARD_CONTROLS_DEFAULTS.search;
    const searchEl = document.getElementById('board-filter-search');

    if (remoteEl) remoteEl.value = remoteFilter;
    if (sizeEl) sizeEl.value = sizeFilter;
    if (recruiterEl) recruiterEl.value = recruiterFilter;
    if (sortEl) sortEl.value = sortBy;
    if (archivedEl) archivedEl.value = archivedFilter;
    if (searchEl) searchEl.value = searchFilter;
    updateBoardSearchClearVisibility();
  }

  function updateArchiveVisibility() {
    const archivedFilter = document.getElementById('board-filter-archived')?.value || 'active';
    localStorage.setItem('boardFilterArchived', archivedFilter);
    loadJobs();
  }

  async function archiveJob(id) {
    const job = findJob(id);
    if (!job) return;
    try {
      const r = await fetch(`/api/jobs/${id}/archive`, { method: 'POST' });
      if (!r.ok) throw new Error('HTTP error ' + r.status);
      const updated = await r.json();
      const action = updated.archived ? 'Archived' : 'Un-archived';
      addLogLine(`${action} [${job.title}] at ${job.company}`, 'info');
      await loadJobs();
    } catch (err) {
      addLogLine(`Failed to toggle archive for [${job.title}]: ${err.message}`, 'warning');
    }
  }

  function toggleLaneCollapse(lane) {
    const wrapper = document.getElementById('lane-' + lane);
    if (!wrapper) return;
    const column = wrapper.closest('.kanban-column');
    if (!column) return;
    const isCollapsed = column.classList.toggle('lane-collapsed');
    localStorage.setItem('kanban-lane-' + lane + '-collapsed', isCollapsed ? 'true' : 'false');
  }

  function initLaneCollapse() {
    const stages = ['scraped', 'matched', 'accepted', 'applied', 'interviewing', 'rejected'];
    stages.forEach(lane => {
      const stored = localStorage.getItem('kanban-lane-' + lane + '-collapsed');
      if (stored === 'true') {
        const wrapper = document.getElementById('lane-' + lane);
        if (wrapper) {
          const column = wrapper.closest('.kanban-column');
          if (column) column.classList.add('lane-collapsed');
        }
      }
    });
  }

  function initKanbanDnd() {
    const stages = ['scraped', 'matched', 'accepted', 'applied', 'interviewing', 'rejected'];
    stages.forEach(lane => {
      const wrapper = document.getElementById('lane-' + lane);
      if (!wrapper) return;
      const column = wrapper.closest('.kanban-column') || wrapper;
      column.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('drag-over');
      });
      column.addEventListener('dragleave', (e) => {
        if (!column.contains(e.relatedTarget)) {
          column.classList.remove('drag-over');
        }
      });
      column.addEventListener('drop', (e) => {
        e.preventDefault();
        column.classList.remove('drag-over');
        const jobId = parseInt(e.dataTransfer.getData('text/plain'), 10);
        if (!jobId) return;
        const job = findJob(jobId);
        if (!job || job.status === lane) return;
        moveJobStage(jobId, lane);
      });
    });
  }

  // ----------------------------------------------------
  // USER ACTIONS & INTERACTIVITY
  // ----------------------------------------------------

  function toggleLaneCollapse(lane) {
    const wrapper = document.getElementById('lane-' + lane);
    if (!wrapper) return;
    const column = wrapper.closest('.kanban-column');
    if (!column) return;
    const isCollapsed = column.classList.toggle('lane-collapsed');
    localStorage.setItem('kanban-lane-' + lane + '-collapsed', isCollapsed ? 'true' : 'false');
  }

  function initLaneCollapse() {
    const stages = ['scraped', 'matched', 'accepted', 'applied', 'interviewing', 'rejected'];
    stages.forEach(lane => {
      const stored = localStorage.getItem('kanban-lane-' + lane + '-collapsed');
      if (stored === 'true') {
        const wrapper = document.getElementById('lane-' + lane);
        if (wrapper) {
          const column = wrapper.closest('.kanban-column');
          if (column) column.classList.add('lane-collapsed');
        }
      }
    });
  }

  function initKanbanDnd() {
    const stages = ['scraped', 'matched', 'accepted', 'applied', 'interviewing', 'rejected'];
    stages.forEach(lane => {
      const wrapper = document.getElementById('lane-' + lane);
      if (!wrapper) return;
      const column = wrapper.closest('.kanban-column') || wrapper;
      column.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('drag-over');
      });
      column.addEventListener('dragleave', (e) => {
        if (!column.contains(e.relatedTarget)) {
          column.classList.remove('drag-over');
        }
      });
      column.addEventListener('drop', (e) => {
        e.preventDefault();
        column.classList.remove('drag-over');
        const jobId = parseInt(e.dataTransfer.getData('text/plain'), 10);
        if (!jobId) return;
        const job = findJob(jobId);
        if (!job || job.status === lane) return;
        moveJobStage(jobId, lane);
      });
    });
  }

  async function enrichJob(id) {
    const job = findJob(id);
    if (!job) return;

    const cacheResp = await fetch(`/api/jobs/${id}/cache-status`);
    if (cacheResp.ok) {
      const cacheData = await cacheResp.json();
      if (cacheData.estimated_runs > 0) {
        const streamLines = (cacheData.billable_streams || [])
          .map(s => `- ${s.stream} — ${s.profile_count} profiles`)
          .join('\n');
        const costStr = `~$${(cacheData.estimated_cost || 0).toFixed(2)}`;
        const runs = cacheData.estimated_runs;
        const ok = await showSpendConfirmModal({
          title: 'Enrich Job',
          subtitle: 'LinkedIn via Apify',
          bodyHtml: buildApifySpendBodyHtml('Enrich Job', streamLines, runs, costStr),
          confirmLabel: 'Proceed',
        });
        if (!ok) return;
      }
    }

    addLogLine(`Initiating enrichment for [${job.title} @ ${job.company}]...`, 'warning');
    expandLogsConsole();

    fetch(`/api/jobs/${id}/enrich`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
      })
      .then(data => {
        if (data.job) {
          if (data.job) updateJob(data.job.id, data.job);
        }
        activeEnrichJobId = data.job_id;
        renderActiveVariant();

        const task_id = data.task_id;
        addLogLine(`Enrichment task started: ${task_id}`, 'info');
        localStorage.setItem(ACTIVE_ENRICH_TASK_KEY, task_id);
        localStorage.setItem(ACTIVE_ENRICH_LOG_SKIP_KEY, '0');

        taskLog.setEnrichEventSource(connectTaskLogStream(task_id, {
          skipKey: ACTIVE_ENRICH_LOG_SKIP_KEY,
          taskKey: ACTIVE_ENRICH_TASK_KEY,
          existingSource: taskLog.getEnrichEventSource(),
          onResult(logData) {
            if (logData.job) {
              if (logData.job) updateJob(logData.job.id, logData.job);
            }
            renderActiveVariant();
          },
          onDone() {
            activeEnrichJobId = null;
            renderActiveVariant();
          },
          onError() {
            activeEnrichJobId = null;
            addLogLine(`Enrichment SSE stream closed for job [${job.title}].`, 'warning');
          },
        }));
      })
      .catch(err => {
        addLogLine(`Failed to trigger enrichment: ${err.message}.`, 'error');
      });
  }

  function markReclassifyActive(jobId, active) {
    if (active) {
      if (!activeReclassifyJobIds.includes(jobId)) {
        activeReclassifyJobIds.push(jobId);
      }
    } else {
      activeReclassifyJobIds = activeReclassifyJobIds.filter((id) => id !== jobId);
    }
  }

  function attachReclassifyStream(taskId, jobId) {
    const skipKey = reclassifyTaskLogSkipKey(taskId);
    const job = findJob(jobId);
    markReclassifyActive(jobId, true);
    renderActiveVariant();
    refreshDrawerIfOpen(jobId);

    taskLog.setReclassifyEventSource(taskId, connectTaskLogStream(taskId, {
      skipKey,
      taskKey: skipKey,
      existingSource: taskLog.getReclassifyEventSource(taskId),
      onResult(logData) {
        if (logData.job) {
          updateJob(logData.job.id, logData.job);
        }
        renderActiveVariant();
        refreshDrawerIfOpen(jobId);
      },
      onDone() {
        removeReclassifyTaskEntry(taskId);
        taskLog.setReclassifyEventSource(taskId, null);
        markReclassifyActive(jobId, false);
        if (job) {
          addLogLine(`Re-classify complete for [${job.title}].`, 'success');
        }
        renderActiveVariant();
        refreshDrawerIfOpen(jobId);
      },
      onError() {
        removeReclassifyTaskEntry(taskId);
        taskLog.setReclassifyEventSource(taskId, null);
        markReclassifyActive(jobId, false);
        addLogLine(
          'Background re-classify task is no longer available on the server.',
          'info'
        );
        renderActiveVariant();
        refreshDrawerIfOpen(jobId);
      },
    }));
  }

  async function startReclassifyTask(id) {
    const job = findJob(id);
    if (!job) return;
    if (activeReclassifyJobIds.includes(id)) return;

    addLogLine(`Re-classifying contacts for [${job.title} @ ${job.company}]...`, 'info');
    expandLogsConsole();

    try {
      const resp = await fetch(`/api/jobs/${id}/reclassify`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        addLogLine(`Re-classify failed: ${err.message || resp.status}`, 'error');
        return;
      }

      const data = await resp.json();
      saveReclassifyTaskEntry(data.task_id, id);
      attachReclassifyStream(data.task_id, id);
    } catch (err) {
      addLogLine(`Re-classify failed: ${err.message}`, 'error');
    }
  }

  function reclassifyJob(id) {
    startReclassifyTask(id);
  }

  async function researchCompany(id) {
    const job = findJob(id);
    if (!job) return;

    const preflightResp = await fetch(`/api/jobs/${id}/company-research-preflight`);
    if (!preflightResp.ok) {
      const err = await preflightResp.json().catch(() => ({}));
      await showSpendAckModal({
        title: 'Cannot research company',
        message: err.message || 'Company research is unavailable for this job.',
      });
      return;
    }

    const preflightData = await preflightResp.json();
    let glassdoorJobTitle = preflightData.default_glassdoor_job_title || job.title;

    if (preflightData.will_call_apify) {
      const ok = await showSpendConfirmModal({
        title: 'Research Company',
        subtitle: 'Glassdoor via Apify',
        bodyHtml: buildGlassdoorSpendBodyHtml(preflightData),
        confirmLabel: 'Proceed',
      });
      if (!ok) return;
      const titleInput = document.getElementById('spend-glassdoor-job-title');
      if (titleInput && titleInput.value.trim()) {
        glassdoorJobTitle = titleInput.value.trim();
      }
    }

    activeCompanyResearchJobId = id;
    renderActiveVariant();
    drawer.refreshDrawerIfOpen(id);
    addLogLine(`Researching [${job.title} @ ${job.company}] on Glassdoor…`, 'info');
    expandLogsConsole();

    try {
      const resp = await fetch(`/api/jobs/${id}/company-research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ glassdoorJobTitle }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        addLogLine(`Company research failed: ${err.message || resp.status}`, 'error');
        return;
      }
      const data = await resp.json();
      const taskId = data.task_id;
      localStorage.setItem(ACTIVE_COMPANY_RESEARCH_TASK_KEY, taskId);
      localStorage.setItem(ACTIVE_COMPANY_RESEARCH_LOG_SKIP_KEY, '0');
      taskLog.setEnrichEventSource(connectTaskLogStream(taskId, {
        skipKey: ACTIVE_COMPANY_RESEARCH_LOG_SKIP_KEY,
        taskKey: ACTIVE_COMPANY_RESEARCH_TASK_KEY,
        existingSource: taskLog.getEnrichEventSource(),
        onResult(logData) {
          if (logData.job) updateJob(logData.job.id, logData.job);
          drawer.refreshDrawerIfOpen(id);
          renderActiveVariant();
        },
        onDone() {
          activeCompanyResearchJobId = null;
          drawer.refreshDrawerIfOpen(id);
          renderActiveVariant();
        },
      }));
    } catch (err) {
      addLogLine(`Company research failed: ${err.message}`, 'error');
    } finally {
      if (!localStorage.getItem(ACTIVE_COMPANY_RESEARCH_TASK_KEY)) {
        activeCompanyResearchJobId = null;
        renderActiveVariant();
        drawer.refreshDrawerIfOpen(id);
      }
    }
  }

  async function loadMoreContacts(id) {
    const job = findJob(id);
    if (!job) return;

    const LOAD_MORE_BLOCKED_MESSAGES = {
      all_streams_exhausted: 'All active streams are exhausted — LinkedIn returned no further profiles.',
      no_audience_toggles: 'No audience toggles active in Contact Search Settings.',
      missing_company_url: 'No LinkedIn company URL — cannot fetch employees.',
    };

    const preflightResp = await fetch(`/api/jobs/${id}/load-more-preflight`);
    if (preflightResp.ok) {
      const preflightData = await preflightResp.json();
      if (preflightData.estimated_runs === 0) {
        const reason = preflightData.blocked_reason || 'unknown';
        await showSpendAckModal({
          title: 'Cannot load more contacts',
          message: LOAD_MORE_BLOCKED_MESSAGES[reason] || 'No streams available to fetch.',
        });
        return;
      }
      const streamLines = (preflightData.billable_streams || [])
        .map(s => `- ${s.stream} — next ${s.profile_count} profiles (page ${s.page})`)
        .join('\n');
      const costStr = `~$${(preflightData.estimated_cost || 0).toFixed(2)}`;
      const runs = preflightData.estimated_runs;
      const ok = await showSpendConfirmModal({
        title: 'Load More Contacts',
        subtitle: 'LinkedIn via Apify',
        bodyHtml: buildApifySpendBodyHtml('Load More Contacts', streamLines, runs, costStr),
        confirmLabel: 'Proceed',
      });
      if (!ok) return;
    }

    activeLoadMoreJobId = id;
    renderActiveVariant();
    refreshDrawerIfOpen(id);
    addLogLine(`Loading more contacts for [${job.title} @ ${job.company}]...`, 'info');
    expandLogsConsole();
    try {
      const resp = await fetch(`/api/jobs/${id}/load-more-contacts`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        addLogLine(`Load More Contacts failed: ${err.message || resp.status}`, 'error');
        return;
      }
      const updated = await resp.json();
      updateJob(updated.id, updated);
      refreshDrawerIfOpen(id);
      addLogLine(`Load More Contacts complete for [${job.title}].`, 'success');
    } catch (err) {
      addLogLine(`Load More Contacts failed: ${err.message}`, 'error');
    } finally {
      activeLoadMoreJobId = null;
      renderActiveVariant();
      refreshDrawerIfOpen(id);
    }
  }

  function deleteJob(id) {
    const job = findJob(id);
    if (job) {
      removeJob(id);
      addLogLine(`Job [${job.title}] deleted from tracker.`, 'error');
      renderActiveVariant();
    }
  }

  function moveJobStage(id, newStatus) {
    const job = findJob(id);
    if (job) {
      const oldStatus = job.status;
      
      // Optimistically update status and render
      job.status = newStatus;
      addLogLine(`Moving card [${job.title}] from '${oldStatus}' to '${newStatus}'...`, 'info');
      renderActiveVariant();

      fetch(`/api/jobs/${id}/status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
      })
      .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
      })
      .then(updatedJob => {
        job.status = updatedJob.status;
        job.activityLog = updatedJob.activityLog || job.activityLog;
        addLogLine(`Successfully moved card [${job.title}] to '${updatedJob.status}' (persisted to DB)`, 'success');
        renderActiveVariant();
      })
      .catch(err => {
        // Revert status on failure
        job.status = oldStatus;
        addLogLine(`Failed to persist status change for [${job.title}]: ${err.message}. Reverted to '${oldStatus}'.`, 'warning');
        renderActiveVariant();
      });
    }
  }

  function changeJobStage(id, newStatus) {
    moveJobStage(id, newStatus);
  }

  function loadJobs() {
    const archivedFilter = getJobsFetchArchivedParam();
    lastJobsFetchArchivedParam = archivedFilter;
    return fetch(`/api/jobs?archived=${archivedFilter}`)
      .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
      })
      .then(data => {
        if (data && data.length > 0) {
          setJobs(data);
          addLogLine(`Loaded ${data.length} jobs dynamically from /api/jobs`, 'success');
        } else {
          setJobs([]);
          addLogLine("Backend returned empty job list. Board is empty.", 'info');
        }
        renderActiveVariant();
      })
      .catch(err => {
        setJobs([]);
        addLogLine("Could not fetch jobs from backend. Board is empty.", 'warning');
        renderActiveVariant();
      });
  }

  function restoreActiveScrapeTask() {
    const taskId = localStorage.getItem(ACTIVE_SCRAPE_TASK_KEY);
    if (!taskId) return;

    const kbLogsPanel = document.getElementById('kb-logs-panel');
    if (kbLogsPanel) {
      kbLogsPanel.style.display = 'block';
    }
    expandLogsConsole();

    const btnPanel = document.getElementById('kb-scrape-btn-panel');
    if (btnPanel) {
      btnPanel.disabled = true;
      btnPanel.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running...';
    }

    addLogLine(`Reconnecting to active background task: ${taskId}`, 'info');

    taskLog.setLogEventSource(connectTaskLogStream(taskId, {
      skipKey: ACTIVE_SCRAPE_LOG_SKIP_KEY,
      taskKey: ACTIVE_SCRAPE_TASK_KEY,
      existingSource: taskLog.getLogEventSource(),
      onResult(logData) {
        integrateSearchResultFromStream(logData);
      },
      onDone() {
        addLogLine('Scraper process complete.', 'success');
        resetScrapeButtons();
      },
      onError() {
        addLogLine(
          'Background scrape task is no longer available on the server.',
          'info'
        );
        resetScrapeButtons();
      },
    }));
  }

  function restoreActiveEnrichTask() {
    const taskId = localStorage.getItem(ACTIVE_ENRICH_TASK_KEY);
    if (!taskId) return;

    const kbLogsPanel = document.getElementById('kb-logs-panel');
    if (kbLogsPanel) kbLogsPanel.style.display = 'block';
    expandLogsConsole();
    addLogLine(`Reconnecting to active enrichment task: ${taskId}`, 'info');
    startPollingEnrichingJobs();

    taskLog.setEnrichEventSource(connectTaskLogStream(taskId, {
      skipKey: ACTIVE_ENRICH_LOG_SKIP_KEY,
      taskKey: ACTIVE_ENRICH_TASK_KEY,
      existingSource: taskLog.getEnrichEventSource(),
      onResult(logData) {
        if (logData.job) {
          updateJob(logData.job.id, logData.job);
        }
        renderActiveVariant();
      },
      onDone() {
        renderActiveVariant();
      },
    }));
  }

  function restoreActiveReclassifyTasks() {
    const tasks = loadReclassifyTaskMap();
    const entries = Object.entries(tasks);
    if (entries.length === 0) return;

    const kbLogsPanel = document.getElementById('kb-logs-panel');
    if (kbLogsPanel) kbLogsPanel.style.display = 'block';
    expandLogsConsole();
    addLogLine(`Reconnecting to ${entries.length} active re-classify task(s)...`, 'info');

    entries.forEach(([taskId, meta]) => {
      attachReclassifyStream(taskId, meta.jobId);
    });
  }

  return {
    archiveJob,
    cancelJobComment,
    cancelOutreachTemplate,
    changeJobStage,
    clearBoardSearch,
    clearLogs,
    closeDrawer,
    copyDrawerOutreach,
    deleteJob,
    enrichJob,
    enrichJobFromDrawer,
    getJobsFetchArchivedParam,
    initBoardControls,
    initKanbanDnd,
    initLaneCollapse,
    integrateSearchResultFromStream,
    loadJobs,
    loadMoreContacts,
    markAppliedFromDrawer,
    moveJobStage,
    navigateDrawerJob,
    onBoardSearchInput,
    onCommentDraftInput,
    onOutreachDraftInput,
    openContactedElsewhereJob,
    openJobDetailsDrawer,
    postJobComment,
    postOutreachTemplate,
    reclassifyJob,
    rejectJobFromDrawer,
    researchCompany,
    renderActiveVariant,
    resetBoardControls,
    restoreActiveEnrichTask,
    restoreActiveReclassifyTasks,
    restoreActiveScrapeTask,
    selectActiveContact,
    toggleActivityLog,
    toggleContacted,
    toggleLaneCollapse,
    updateArchiveVisibility,
    updateBoardFiltersAndSort,
    updateDrawerNav,
    updateOutreachCounter,
  };
}
