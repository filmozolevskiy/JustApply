/** Profile Manager — list, edit, create, delete, import, and active Resume Profile selection. */

import { getJobs } from './jobStore.js';

export function createProfileManagerController({ addLogLine, onActiveResumeChanged }) {
  const ACTIVE_RESUME_KEY = 'activeResumeProfile';
  let mockResumes = {};
  let activeResume = null;
  let profileManagerProfiles = [];
  let profileManagerSelectedName = null;
  let profileManagerReviewing = false;
  let profileManagerLastRenderedKey = null;
  let profileManagerDraftContent = null;

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
    onActiveResumeChanged?.();
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

  function initProfileManagerImportInput() {
    const pmImportInput = document.getElementById('pm-import-input');
    if (pmImportInput) {
      pmImportInput.addEventListener('change', handleProfileManagerImportFile);
    }
  }

  return {
    closeProfileManager,
    deleteProfileManagerProfile,
    getActiveResume: () => activeResume,
    handleProfileManagerImportFile,
    initProfileManagerImportInput,
    loadResumes,
    newProfileManagerProfile,
    openProfileManager,
    saveProfileManagerProfile,
    selectProfileManagerProfile,
    setActiveProfileManagerProfile,
    triggerProfileManagerImport,
  };
}
