/** Dashboard bootstrap — wires modules and outreach settings. */

import { createBoardOrchestrator } from './boardOrchestration.js';
import { createEvaluationLockController } from './evaluationLock.js';
import { createJobSearchSettingsController } from './jobSearchSettings.js';
import { createProfileManagerController } from './profileManager.js';
import {
  confirmDiscardUnsavedEdits,
  dismissSpendModalFromOverlay,
} from './spendConfirmation.js';
import { createDrawerController } from './drawerController.js';
import { createTaskLogClient } from './taskLogClient.js';

export function bootstrapDashboard() {
  const taskLog = createTaskLogClient();
  const {
    addLogLine,
    clearLogs,
    connectTaskLogStream,
    closeTaskLogStreamQuietly,
    expandLogsConsole,
    markPageUnloading,
    restoreSessionLogs,
  } = taskLog;

  let jobSearchSettings;
  let evaluationLock;
  let board;
  let profileManager;

  evaluationLock = createEvaluationLockController({
    addLogLine,
    onLockStateChange: () => jobSearchSettings?.updateScrapeRunButtonState(),
  });

  board = createBoardOrchestrator({
    addLogLine,
    clearLogs,
    closeTaskLogStreamQuietly,
    confirmDiscardUnsavedEdits,
    connectTaskLogStream,
    createDrawerController,
    expandLogsConsole,
    resetScrapeButtons: () => jobSearchSettings?.resetScrapeButtons(),
    taskLog,
  });

  profileManager = createProfileManagerController({
    addLogLine,
    onActiveResumeChanged: () => board.renderActiveVariant(),
  });

  jobSearchSettings = createJobSearchSettingsController({
    addLogLine,
    closeTaskLogStreamQuietly,
    connectTaskLogStream,
    expandLogsConsole,
    getActiveResume: () => profileManager.getActiveResume(),
    integrateSearchResultFromStream: board.integrateSearchResultFromStream,
    isEvaluationLockActive: () => evaluationLock.isEvaluationLockActive(),
    taskLog,
  });

  async function loadOutreachSettings() {
    try {
      const resp = await fetch('/api/settings/outreach');
      if (!resp.ok) return;
      const s = await resp.json();
      document.getElementById('toggle-short-connection-note').checked = s.short_connection_note !== false;
      document.getElementById('toggle-russian-speakers').checked = !!s.target_russian_speakers;
      document.getElementById('toggle-recruiters').checked = !!s.target_recruiters;
      syncOutreachCardVisuals();
    } catch (e) { console.error('Failed to load outreach settings', e); }
  }

  function syncOutreachCardVisuals() {
    const keys = ['short_connection_note', 'target_russian_speakers', 'target_recruiters'];
    const ids = ['toggle-short-connection-note', 'toggle-russian-speakers', 'toggle-recruiters'];
    keys.forEach((key, i) => {
      const cb = document.getElementById(ids[i]);
      const card = document.querySelector(`[data-outreach-card="${key}"]`);
      if (!cb || !card) return;
      card.classList.toggle('on', cb.checked);
      card.setAttribute('aria-checked', cb.checked ? 'true' : 'false');
    });
  }

  function onOutreachToggle(key, value) {
    syncOutreachCardVisuals();
    saveOutreachSettings(key, value);
  }

  function initOutreachToggleHandlers() {
    const configs = [
      { key: 'short_connection_note', id: 'toggle-short-connection-note' },
      { key: 'target_russian_speakers', id: 'toggle-russian-speakers' },
      { key: 'target_recruiters', id: 'toggle-recruiters' },
    ];

    configs.forEach(({ key, id }) => {
      const cb = document.getElementById(id);
      const card = document.querySelector(`[data-outreach-card="${key}"]`);
      if (!cb || !card) return;

      const toggle = cb.closest('.toggle-switch');
      if (toggle) {
        const stopCardToggle = (event) => event.stopPropagation();
        toggle.addEventListener('click', stopCardToggle);
        toggle.addEventListener('mousedown', stopCardToggle);
      }

      cb.addEventListener('change', () => {
        onOutreachToggle(key, cb.checked);
      });

      card.addEventListener('click', (event) => {
        if (event.target.closest('.toggle-switch')) return;
        cb.checked = !cb.checked;
        syncOutreachCardVisuals();
        saveOutreachSettings(key, cb.checked);
      });
    });
  }

  async function saveOutreachSettings(key, value) {
    try {
      const current = {
        short_connection_note: document.getElementById('toggle-short-connection-note').checked,
        target_russian_speakers: document.getElementById('toggle-russian-speakers').checked,
        target_recruiters: document.getElementById('toggle-recruiters').checked,
      };
      current[key] = value;
      await fetch('/api/settings/outreach', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(current),
      });
    } catch (e) { console.error('Failed to save outreach setting', e); }
  }

  function initOutreachSettingsTooltips() {
    const delayMs = 1000;
    const margin = 8;
    let floatingTooltip = document.getElementById('outreach-settings-floating-tooltip');
    if (!floatingTooltip) {
      floatingTooltip = document.createElement('div');
      floatingTooltip.id = 'outreach-settings-floating-tooltip';
      floatingTooltip.className = 'settings-tooltip-floating';
      floatingTooltip.setAttribute('role', 'tooltip');
      document.body.appendChild(floatingTooltip);
    }

    let showTimer = null;

    const hideTooltip = () => {
      if (showTimer) {
        clearTimeout(showTimer);
        showTimer = null;
      }
      floatingTooltip.classList.remove('is-visible');
      floatingTooltip.style.left = '';
      floatingTooltip.style.top = '';
    };

    const positionTooltip = (wrap) => {
      floatingTooltip.textContent = wrap.dataset.tooltip || '';
      floatingTooltip.classList.add('is-visible');

      const rect = wrap.getBoundingClientRect();
      floatingTooltip.style.left = '0px';
      floatingTooltip.style.top = '0px';
      const tooltipRect = floatingTooltip.getBoundingClientRect();

      let left = rect.left;
      if (left + tooltipRect.width > window.innerWidth - margin) {
        left = window.innerWidth - tooltipRect.width - margin;
      }
      left = Math.max(margin, left);

      let top = rect.top - tooltipRect.height - margin;
      if (top < margin) {
        top = rect.bottom + margin;
      }

      floatingTooltip.style.left = `${left}px`;
      floatingTooltip.style.top = `${top}px`;
    };

    document.querySelectorAll('.settings-tooltip-wrap[data-tooltip]').forEach((wrap) => {
      wrap.addEventListener('mouseenter', () => {
        hideTooltip();
        showTimer = setTimeout(() => {
          positionTooltip(wrap);
          showTimer = null;
        }, delayMs);
      });
      wrap.addEventListener('mouseleave', hideTooltip);
    });

    window.addEventListener('scroll', hideTooltip, true);
    window.addEventListener('resize', hideTooltip);
  }

  window.addEventListener('beforeunload', markPageUnloading);
  window.addEventListener('pagehide', () => {
    markPageUnloading();
    closeTaskLogStreamQuietly(taskLog.getLogEventSource());
    taskLog.setLogEventSource(null);
    closeTaskLogStreamQuietly(taskLog.getEnrichEventSource());
    taskLog.setEnrichEventSource(null);
    for (const source of taskLog.getReclassifyEventSources().values()) {
      closeTaskLogStreamQuietly(source);
    }
    for (const taskId of [...taskLog.getReclassifyEventSources().keys()]) {
      taskLog.setReclassifyEventSource(taskId, null);
    }
  });

  Object.assign(window, {
    archiveJob: board.archiveJob,
    cancelEvaluation: evaluationLock.cancelEvaluation,
    cancelJobComment: board.cancelJobComment,
    cancelOutreachTemplate: board.cancelOutreachTemplate,
    changeJobStage: board.changeJobStage,
    clearBoardSearch: board.clearBoardSearch,
    clearLogs: board.clearLogs,
    closeDrawer: board.closeDrawer,
    closeProfileManager: profileManager.closeProfileManager,
    copyDrawerOutreach: board.copyDrawerOutreach,
    deleteProfileManagerProfile: profileManager.deleteProfileManagerProfile,
    dismissSpendModalFromOverlay,
    enrichJob: board.enrichJob,
    enrichJobFromDrawer: board.enrichJobFromDrawer,
    loadMoreContacts: board.loadMoreContacts,
    markAppliedFromDrawer: board.markAppliedFromDrawer,
    moveJobStage: board.moveJobStage,
    navigateDrawerJob: board.navigateDrawerJob,
    newProfileManagerProfile: profileManager.newProfileManagerProfile,
    onBoardSearchInput: board.onBoardSearchInput,
    onCommentDraftInput: board.onCommentDraftInput,
    onOutreachDraftInput: board.onOutreachDraftInput,
    openContactedElsewhereJob: board.openContactedElsewhereJob,
    openJobDetailsDrawer: board.openJobDetailsDrawer,
    openProfileManager: profileManager.openProfileManager,
    postJobComment: board.postJobComment,
    postOutreachTemplate: board.postOutreachTemplate,
    reclassifyJob: board.reclassifyJob,
    rejectJobFromDrawer: board.rejectJobFromDrawer,
    researchCompany: board.researchCompany,
    resetBoardControls: board.resetBoardControls,
    resetKbFilters: jobSearchSettings.resetKbFilters,
    saveOutreachSettings,
    saveProfileManagerProfile: profileManager.saveProfileManagerProfile,
    selectActiveContact: board.selectActiveContact,
    selectProfileManagerProfile: profileManager.selectProfileManagerProfile,
    setActiveProfileManagerProfile: profileManager.setActiveProfileManagerProfile,
    toggleActivityLog: board.toggleActivityLog,
    toggleContacted: board.toggleContacted,
    toggleJobSearchSettings: jobSearchSettings.toggleJobSearchSettings,
    toggleLaneCollapse: board.toggleLaneCollapse,
    toggleLogsHeight: jobSearchSettings.toggleLogsHeight,
    triggerProfileManagerImport: profileManager.triggerProfileManagerImport,
    triggerScrapeRun: jobSearchSettings.triggerScrapeRun,
    updateArchiveVisibility: board.updateArchiveVisibility,
    updateBoardFiltersAndSort: board.updateBoardFiltersAndSort,
    updateOutreachCounter: board.updateOutreachCounter,
  });

  board.initBoardControls();
  board.initKanbanDnd();
  board.initLaneCollapse();
  jobSearchSettings.initLogsConsoleState();
  jobSearchSettings.initJobSearchSettingsState();
  jobSearchSettings.initSearchRegionPickers();
  jobSearchSettings.initPerRegionLimitStepper();
  initOutreachSettingsTooltips();
  initOutreachToggleHandlers();
  evaluationLock.initEvaluationLockPolling();
  restoreSessionLogs();
  profileManager.initProfileManagerImportInput();
  profileManager.loadResumes();
  loadOutreachSettings();
  board.loadJobs().then(() => {
    board.restoreActiveScrapeTask();
    board.restoreActiveEnrichTask();
    board.restoreActiveReclassifyTasks();
  });
}
