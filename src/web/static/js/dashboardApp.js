/** Dashboard bootstrap — wires modules, Profile Manager, and outreach settings. */

import { getJobs } from './jobStore.js';
import { createBoardOrchestrator } from './boardOrchestration.js';
import { createEvaluationLockController } from './evaluationLock.js';
import { createJobSearchSettingsController } from './jobSearchSettings.js';
import {
  confirmDiscardUnsavedEdits,
  dismissSpendModalFromOverlay,
} from './spendConfirmation.js';
import { createDrawerController } from './drawerController.js';
import { createTaskLogClient } from './taskLogClient.js';

export function bootstrapDashboard() {
  let mockResumes = {};
  const ACTIVE_RESUME_KEY = 'activeResumeProfile';
  let activeResume = null;
  let profileManagerProfiles = [];
  let profileManagerSelectedName = null;
  let profileManagerReviewing = false;
  let profileManagerLastRenderedKey = null;
  let profileManagerDraftContent = null;

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

  jobSearchSettings = createJobSearchSettingsController({
    addLogLine,
    closeTaskLogStreamQuietly,
    connectTaskLogStream,
    expandLogsConsole,
    getActiveResume: () => activeResume,
    integrateSearchResultFromStream: board.integrateSearchResultFromStream,
    isEvaluationLockActive: () => evaluationLock.isEvaluationLockActive(),
    taskLog,
  });

  function resolveActiveResume(profiles, storedName) {
    if (!profiles || profiles.length === 0) return null;
    const names = profiles.map(p => p.name);
    if (storedName && names.includes(storedName)) return storedName;
    return profiles[0].name;
  }

  function persistActiveResume(name) {
    if (name) {
      localStorage.setItem(ACTIVE_RESUME_KEY, name);
    }
  }

  function openProfileManager() {
    const modal = document.getElementById('profile-manager-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    renderProfileManager();
  }

  function closeProfileManager(e) {
    const modal = document.getElementById('profile-manager-modal');
    if (!modal) return;
    if (!e || e.target === modal || e.target.classList.contains('modal-close') || e.target.closest('.modal-close')) {
      modal.style.display = 'none';
    }
  }

  function renderProfileManager() {
    const listEl = document.getElementById('pm-list-scroll');
    const titleWrap = document.getElementById('pm-detail-title-wrap');
    const editorEl = document.getElementById('pm-editor');
    const setActiveBtn = document.getElementById('pm-set-active-btn');
    const deleteBtn = document.getElementById('pm-delete-btn');
    const saveBtn = document.getElementById('pm-save-btn');
    const reviewBanner = document.getElementById('pm-review-banner');
    if (!listEl) return;

    if (profileManagerProfiles.length === 0 && !profileManagerReviewing) {
      listEl.innerHTML = '<div style="padding:12px;color:var(--text-muted)">No profiles found.</div>';
      if (titleWrap) titleWrap.innerHTML = '';
      if (editorEl) editorEl.value = '';
      if (setActiveBtn) setActiveBtn.disabled = true;
      if (deleteBtn) deleteBtn.disabled = true;
      if (saveBtn) saveBtn.disabled = true;
      if (reviewBanner) reviewBanner.hidden = true;
      return;
    }

    if (!profileManagerReviewing) {
      if (!profileManagerSelectedName || !profileManagerProfiles.find(p => p.name === profileManagerSelectedName)) {
        profileManagerSelectedName = profileManagerProfiles[0]?.name ?? null;
      }
    }

    const selected = profileManagerProfiles.find(p => p.name === profileManagerSelectedName);

    listEl.innerHTML = profileManagerProfiles.map(p => `
      <div class="pm-li ${p.name === profileManagerSelectedName && !profileManagerReviewing ? 'sel' : ''}" data-name="${p.name}" onclick="selectProfileManagerProfile(this.dataset.name)">
        <i class="fa-regular fa-file-lines pm-doc"></i>
        <span class="pm-nm">${p.name}</span>
        ${p.name === activeResume ? '<span class="active-chip">Active</span>' : ''}
      </div>
    `).join('');

    if (profileManagerReviewing) {
      if (titleWrap) {
        titleWrap.innerHTML = '<input class="pm-name-input" id="pm-name-input" type="text" placeholder="Profile name (e.g. senior_qa)" />';
      }
      if (reviewBanner) reviewBanner.hidden = false;
      if (setActiveBtn) setActiveBtn.disabled = true;
      if (deleteBtn) deleteBtn.disabled = true;
      if (saveBtn) saveBtn.disabled = false;
    } else {
      if (titleWrap) {
        titleWrap.innerHTML = `<h3 style="font-size:1.05rem">${selected?.name ?? ''}</h3>`;
      }
      if (reviewBanner) reviewBanner.hidden = true;
      if (setActiveBtn) {
        setActiveBtn.disabled = !selected || selected.name === activeResume;
        setActiveBtn.innerHTML = selected && selected.name === activeResume
          ? '<i class="fa-solid fa-star"></i> Active'
          : '<i class="fa-solid fa-star"></i> Set active';
      }
      if (deleteBtn) {
        const canDelete = selected
          && selected.name !== activeResume
          && profileManagerProfiles.length > 1;
        deleteBtn.disabled = !canDelete;
      }
      if (saveBtn) saveBtn.disabled = !selected;
    }

    const renderKey = profileManagerReviewing ? 'review' : (profileManagerSelectedName || 'none');
    if (editorEl && renderKey !== profileManagerLastRenderedKey) {
      if (profileManagerReviewing) {
        editorEl.value = profileManagerDraftContent ?? '';
      } else if (selected) {
        editorEl.value = selected.content;
      }
      profileManagerLastRenderedKey = renderKey;
    }
  }

  function triggerProfileManagerImport() {
    const input = document.getElementById('pm-import-input');
    if (input) input.click();
  }

  async function handleProfileManagerImportFile(event) {
    const input = event.target;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      addLogLine('Only PDF files are supported for import.', 'warning');
      return;
    }

    const importBtn = document.getElementById('pm-import-btn');
    const prevLabel = importBtn?.innerHTML;
    if (importBtn) {
      importBtn.disabled = true;
      importBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Converting…';
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/api/resumes/convert', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        addLogLine(err.detail || 'Resume import failed.', 'error');
        return;
      }

      const data = await response.json();
      profileManagerDraftContent = data.content ?? '';
      profileManagerReviewing = true;
      profileManagerSelectedName = null;
      profileManagerLastRenderedKey = null;
      addLogLine('PDF converted — review and save when ready.', 'success');
      renderProfileManager();
    } catch (err) {
      addLogLine(`Resume import failed: ${err}`, 'error');
    } finally {
      if (importBtn) {
        importBtn.disabled = false;
        importBtn.innerHTML = prevLabel || '<i class="fa-solid fa-file-arrow-up"></i> Import PDF';
      }
    }
  }

  function newProfileManagerProfile() {
    profileManagerReviewing = true;
    profileManagerSelectedName = null;
    profileManagerDraftContent = null;
    profileManagerLastRenderedKey = null;
    renderProfileManager();
  }

  async function saveProfileManagerProfile() {
    const editorEl = document.getElementById('pm-editor');
    const content = editorEl?.value ?? '';

    try {
      let response;
      if (profileManagerReviewing) {
        const nameInput = document.getElementById('pm-name-input');
        const name = nameInput?.value?.trim();
        if (!name) {
          addLogLine('Profile name is required before save.', 'warning');
          return;
        }
        response = await fetch('/api/resumes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, content }),
        });
      } else if (profileManagerSelectedName) {
        response = await fetch('/api/resumes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: profileManagerSelectedName, content }),
        });
      } else {
        return;
      }

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        addLogLine(err.detail || 'Failed to save resume profile.', 'error');
        return;
      }

      const saved = await response.json();
      mockResumes[saved.name] = saved.content;
      const existingIdx = profileManagerProfiles.findIndex(p => p.name === saved.name);
      if (existingIdx >= 0) {
        profileManagerProfiles[existingIdx] = saved;
      } else {
        profileManagerProfiles.push(saved);
        profileManagerProfiles.sort((a, b) => a.name.localeCompare(b.name));
      }
      profileManagerReviewing = false;
      profileManagerSelectedName = saved.name;
      profileManagerDraftContent = null;
      profileManagerLastRenderedKey = null;
      addLogLine(`Saved resume profile: ${saved.name}`, 'success');
      renderProfileManager();
    } catch (err) {
      addLogLine(`Failed to save resume profile: ${err}`, 'error');
    }
  }

  function selectProfileManagerProfile(name) {
    profileManagerReviewing = false;
    profileManagerSelectedName = name;
    profileManagerDraftContent = null;
    profileManagerLastRenderedKey = null;
    renderProfileManager();
  }

  function setActiveProfileManagerProfile() {
    if (!profileManagerSelectedName) return;
    activeResume = profileManagerSelectedName;
    persistActiveResume(activeResume);
    addLogLine(`Active resume profile set to: ${activeResume}`, 'success');
    getJobs().forEach(job => {
      if (job.status === 'scraped' || job.status === 'matched') {
        job.resumeUsed = activeResume;
      }
    });
    renderProfileManager();
    board.renderActiveVariant();
  }

  async function deleteProfileManagerProfile() {
    if (!profileManagerSelectedName || profileManagerReviewing) return;
    const target = profileManagerSelectedName;
    if (target === activeResume) {
      addLogLine('Cannot delete the Active Resume Profile. Set another profile active first.', 'warning');
      return;
    }
    if (profileManagerProfiles.length <= 1) {
      addLogLine('Cannot delete the last remaining resume profile.', 'warning');
      return;
    }
    const ok = confirm(`Delete resume profile "${target}"? This cannot be undone.`);
    if (!ok) return;

    try {
      const response = await fetch(
        `/api/resumes/${encodeURIComponent(target)}?active_resume=${encodeURIComponent(activeResume || '')}`,
        { method: 'DELETE' },
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        addLogLine(err.detail || 'Failed to delete resume profile.', 'error');
        return;
      }

      delete mockResumes[target];
      profileManagerProfiles = profileManagerProfiles.filter(p => p.name !== target);
      profileManagerSelectedName = profileManagerProfiles[0]?.name ?? null;
      profileManagerLastRenderedKey = null;
      addLogLine(`Deleted resume profile: ${target}`, 'success');
      renderProfileManager();
    } catch (err) {
      addLogLine(`Failed to delete resume profile: ${err}`, 'error');
    }
  }

  function loadResumes() {
    return fetch('/api/resumes')
      .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
      })
      .then(data => {
        if (data && data.length > 0) {
          mockResumes = {};
          data.forEach((resume) => {
            mockResumes[resume.name] = resume.content;
          });
          profileManagerProfiles = data;
          const stored = localStorage.getItem(ACTIVE_RESUME_KEY);
          activeResume = resolveActiveResume(data, stored);
          if (activeResume) {
            persistActiveResume(activeResume);
          }
          addLogLine(`Loaded ${data.length} resume profiles dynamically from /api/resumes`, 'success');
        }
      })
      .catch(err => {
        addLogLine("Could not fetch resumes from backend.", 'warning');
      });
  }

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
    closeProfileManager,
    copyDrawerOutreach: board.copyDrawerOutreach,
    dismissSpendModalFromOverlay,
    enrichJob: board.enrichJob,
    enrichJobFromDrawer: board.enrichJobFromDrawer,
    loadMoreContacts: board.loadMoreContacts,
    markAppliedFromDrawer: board.markAppliedFromDrawer,
    moveJobStage: board.moveJobStage,
    navigateDrawerJob: board.navigateDrawerJob,
    onBoardSearchInput: board.onBoardSearchInput,
    onCommentDraftInput: board.onCommentDraftInput,
    onOutreachDraftInput: board.onOutreachDraftInput,
    triggerProfileManagerImport,
    newProfileManagerProfile,
    openProfileManager,
    postJobComment: board.postJobComment,
    postOutreachTemplate: board.postOutreachTemplate,
    reclassifyJob: board.reclassifyJob,
    openContactedElsewhereJob: board.openContactedElsewhereJob,
    openJobDetailsDrawer: board.openJobDetailsDrawer,
    rejectJobFromDrawer: board.rejectJobFromDrawer,
    resetBoardControls: board.resetBoardControls,
    resetKbFilters: jobSearchSettings.resetKbFilters,
    saveOutreachSettings,
    selectActiveContact: board.selectActiveContact,
    saveProfileManagerProfile,
    selectProfileManagerProfile,
    deleteProfileManagerProfile,
    setActiveProfileManagerProfile,
    toggleActivityLog: board.toggleActivityLog,
    toggleContacted: board.toggleContacted,
    toggleJobSearchSettings: jobSearchSettings.toggleJobSearchSettings,
    toggleLaneCollapse: board.toggleLaneCollapse,
    toggleLogsHeight: jobSearchSettings.toggleLogsHeight,
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
  const pmImportInput = document.getElementById('pm-import-input');
  if (pmImportInput) {
    pmImportInput.addEventListener('change', handleProfileManagerImportFile);
  }
  loadResumes();
  loadOutreachSettings();
  board.loadJobs().then(() => {
    board.restoreActiveScrapeTask();
    board.restoreActiveEnrichTask();
    board.restoreActiveReclassifyTasks();
  });
}
