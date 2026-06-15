/** Job details drawer — Active Contact, templates, and outreach UI. */

import { findJob, updateJob } from './jobStore.js';

export const NAME_PLACEHOLDER = '______';

export function applyGreetingName(template, firstName) {
  return template.replace(/^((?:Hello|Hi|Dear)\s+)\S+,/m, `$1${firstName},`);
}

export function normalizeGreeting(template) {
  return template.replace(/^((?:Hello|Hi|Dear)\s+)\S+,/m, `$1${NAME_PLACEHOLDER},`);
}

export function contactGroup(contact) {
  if (contact.is_recruiter) return 'recruiters';
  if (contact.russian_speaker) return 'russian_speakers';
  return 'other';
}

export function getActiveTemplate(job, contactIdx) {
  const contacts = job.contacts || [];
  const contact = contacts[contactIdx];
  if (contact && contact.is_recruiter) {
    return job.recruiterOutreachTemplate || job.outreachMessage || '';
  }
  return job.russianSpeakerOutreachTemplate || job.outreachMessage || '';
}

export function buildContactGroupsHtml(jobId, contacts, activeContactIdx) {
  if (contacts.length === 0) {
    return '<p style="font-size:0.8rem; color:var(--text-muted); text-align:center;">No contacts listed.</p>';
  }
  const GROUPS = [
    { key: 'recruiters', label: 'Recruiters', items: [] },
    { key: 'russian_speakers', label: 'Russian Speakers', items: [] },
    { key: 'other', label: 'Other', items: [] },
  ];
  contacts.forEach((contact, origIdx) => {
    const key = contactGroup(contact);
    const g = GROUPS.find((gr) => gr.key === key);
    if (g) g.items.push({ contact, origIdx });
  });
  return GROUPS.filter((g) => g.items.length > 0)
    .map(
      (group) => `
        <div style="display:flex; flex-direction:column; gap:6px;">
          <div style="font-size:0.68rem; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); padding:0 4px; margin-top:4px;">${group.label}</div>
          ${group.items
            .map(
              ({ contact, origIdx }) => `
            <div id="contact-row-${jobId}-${origIdx}"
              onclick="selectActiveContact(${jobId}, ${origIdx})"
              style="display:flex; align-items:center; justify-content:space-between; background:rgba(0,0,0,0.18); padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.02); border-left:${origIdx === activeContactIdx ? '3px solid var(--accent-cyan)' : '3px solid transparent'}; cursor:pointer;">
              <div style="display:flex; align-items:center; gap:10px;">
                <input type="checkbox" id="contact-${jobId}-${origIdx}" ${contact.contacted ? 'checked' : ''} onclick="event.stopPropagation()" onchange="toggleContacted(${jobId}, ${origIdx}, this.checked)" style="width:16px; height:16px; cursor:pointer;">
                <div style="display:flex; flex-direction:column;">
                  <span style="font-size:0.85rem; font-weight:500; color:${contact.contacted ? 'var(--accent-emerald)' : 'var(--text-primary)'};">
                    ${contact.name}
                    ${contact.contacted ? '<span style="font-size:0.65rem; background:rgba(16,185,129,0.15); color:#34d399; padding:1px 6px; border-radius:10px; margin-left:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Contacted</span>' : ''}
                    ${contact.russian_speaker ? '<span style="font-size:0.65rem; background:rgba(239,68,68,0.15); color:#f87171; padding:1px 6px; border-radius:10px; margin-left:4px; font-weight:600; letter-spacing:0.04em;">🇷🇺 RU</span>' : ''}
                    ${contact.is_recruiter ? '<span style="font-size:0.65rem; background:rgba(99,102,241,0.15); color:#a5b4fc; padding:1px 6px; border-radius:10px; margin-left:4px; font-weight:600; letter-spacing:0.04em;">🎯 HR</span>' : ''}
                    ${contact.is_job_poster ? '<span style="font-size:0.65rem; background:rgba(245,158,11,0.15); color:#fbbf24; padding:1px 6px; border-radius:10px; margin-left:4px; font-weight:600; letter-spacing:0.04em;">📋 Poster</span>' : ''}
                  </span>
                  <span style="font-size:0.75rem; color:var(--text-secondary);">${contact.title || contact.role || ''}</span>
                </div>
              </div>
              <a href="${contact.url || contact.linkedin || '#'}" target="_blank" onclick="event.stopPropagation()" style="color:#0077b5; font-size:1.15rem; padding:4px;" title="View LinkedIn Profile"><i class="fa-brands fa-linkedin"></i></a>
            </div>
          `,
            )
            .join('')}
        </div>
      `,
    )
    .join('');
}

export function createDrawerController({ onJobMutated, addLogLine }) {
  let activeContactIdx = -1;
  let commentTimeout = null;
  let templateSaveTimeout = null;

  function selectActiveContact(jobId, contactIdx) {
    activeContactIdx = contactIdx;
    const job = findJob(jobId);
    if (!job) return;

    const contacts = job.contacts || [];
    contacts.forEach((_, i) => {
      const row = document.getElementById(`contact-row-${jobId}-${i}`);
      if (row) {
        row.style.borderLeft =
          i === contactIdx ? '3px solid var(--accent-cyan)' : '3px solid transparent';
      }
    });

    const textarea = document.getElementById('drawer-outreach-text');
    const counter = document.getElementById('drawer-char-counter');
    const rawTemplate = getActiveTemplate(job, contactIdx);
    const contact = contacts[contactIdx];
    const firstName = contact ? contact.name.split(' ')[0] : '';
    const template = firstName ? applyGreetingName(rawTemplate, firstName) : rawTemplate;
    if (textarea) {
      textarea.value = template;
      if (counter) {
        const len = template.length;
        counter.textContent = `${len}/200`;
        counter.style.color = len > 200 ? 'var(--accent-rose)' : 'var(--text-muted)';
      }
    }
  }

  function openJobDetailsDrawer(id) {
    const job = findJob(id);
    if (!job) return;

    const overlay = document.getElementById('kanban-drawer');
    const body = document.getElementById('drawer-body');

    let matchClass = 'match-low';
    if (job.matchScore >= 85) matchClass = 'match-high';
    else if (job.matchScore >= 70) matchClass = 'match-mid';

    let displayGaps = [...(job.gaps || [])];
    if (
      job.isRecruiter &&
      !displayGaps.some(
        (g) =>
          g.toLowerCase().includes('recruiting agency') ||
          g.toLowerCase().includes('staffing firm'),
      )
    ) {
      displayGaps.push('Posted by a recruiting agency/staffing firm');
    }

    const contacts = job.contacts || [];
    let defaultContactIdx = contacts.findIndex((c) => !c.contacted);
    if (defaultContactIdx === -1) defaultContactIdx = contacts.length > 0 ? 0 : -1;
    activeContactIdx = defaultContactIdx;

    const rawActiveTemplate = activeContactIdx >= 0 ? getActiveTemplate(job, activeContactIdx) : '';
    const defaultContact = activeContactIdx >= 0 ? contacts[activeContactIdx] : null;
    const defaultFirstName = defaultContact ? defaultContact.name.split(' ')[0] : '';
    const activeTemplate = defaultFirstName
      ? applyGreetingName(rawActiveTemplate, defaultFirstName)
      : rawActiveTemplate;

    body.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid var(--border-color); padding-bottom:16px; margin-bottom:16px;">
          <div>
            <h2 style="font-size:1.4rem; color:var(--text-primary); display:flex; align-items:center; gap:8px;">
              ${job.title}
              <a href="${job.link}" target="_blank" style="color:#06b6d4; font-size:1.15rem;" title="View LinkedIn Posting"><i class="fa-brands fa-linkedin"></i></a>
            </h2>
            <div style="color:var(--text-secondary); margin-top:4px; font-size:0.9rem;">
              <strong>${job.company}</strong> &bull; ${job.location} &bull; ${job.salary || 'Not specified'}
            </div>
          </div>
          <span class="match-pill ${matchClass}" style="font-size:1.1rem; padding: 4px 10px;">${job.matchScore}% Match</span>
        </div>

        ${job.isRecruiter ? `
          <div style="background: linear-gradient(90deg, rgba(244, 63, 94, 0.1) 0%, rgba(245, 158, 11, 0.1) 100%); border: 1px solid rgba(244, 63, 94, 0.25); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 0.85rem; color: #f43f5e; display: flex; align-items: center; gap: 10px;">
            <i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; font-size:1.15rem; flex-shrink:0;"></i>
            <span><strong>Recruiting / Staffing Agency Warning:</strong> This job posting was published by a recruitment or staffing agency, not directly by the employer. The match score has been penalized by 15 points.</span>
          </div>
        ` : ''}

        <div style="display:flex; flex-direction:column; gap:14px;">
          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Job Info</h4>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; font-size:0.85rem; color:var(--text-secondary);">
              <div>Status: <span class="status-badge status-${job.status}" style="font-size:0.65rem; padding: 2px 6px;">${job.status}</span></div>
              <div>Seniority: <span style="text-transform:capitalize;">${job.seniority}</span></div>
              <div>Remote Policy: <span style="text-transform:capitalize;">${job.remoteType}</span></div>
              <div>Resume Profile: <code>${job.resumeUsed}</code></div>
            </div>
          </div>

          ${job.activityLog && job.activityLog.length > 0
            ? (() => {
                const log = job.activityLog;
                const latest = log[log.length - 1];
                const logId = 'activity-log-' + job.id;
                return `
          <div>
            <button onclick="toggleActivityLog('${logId}')" style="background:none; border:none; cursor:pointer; display:flex; align-items:center; gap:6px; padding:0; width:100%; text-align:left; margin-bottom:0;">
              <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin:0;">Job Activity Log</h4>
              <i id="${logId}-chevron" class="fa-solid fa-chevron-right" style="font-size:0.65rem; color:var(--text-muted); transition:transform 0.2s;"></i>
              <span style="font-size:0.78rem; color:var(--text-secondary); font-weight:400; text-transform:none; letter-spacing:0; margin-left:4px;">${latest.message}</span>
            </button>
            <div id="${logId}" style="display:none; margin-top:8px; border-left:2px solid rgba(6,182,212,0.2); padding-left:10px; flex-direction:column; gap:4px;">
              ${log
                .map((e) => {
                  const d = new Date(e.ts);
                  const now = new Date();
                  const isToday = d.toDateString() === now.toDateString();
                  const timeStr = isToday
                    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) +
                      ' ' +
                      d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                  return `<div style="display:flex; gap:8px; font-size:0.78rem;">
                  <span style="color:var(--text-muted); white-space:nowrap; flex-shrink:0;">${timeStr}</span>
                  <span style="color:var(--text-secondary);">${e.message}</span>
                </div>`;
                })
                .join('')}
            </div>
          </div>`;
              })()
            : ''}

          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Description</h4>
            <div class="detail-description" style="font-size:0.85rem; max-height: 150px; overflow-y: auto;">${job.description}</div>
          </div>

          <div class="match-breakdown">
            <div class="match-factor-box" style="padding:10px;">
              <div class="factor-title strengths" style="font-size:0.75rem;"><i class="fa-solid fa-circle-check"></i> Strengths</div>
              <ul class="factor-list" style="font-size:0.75rem;">
                ${job.strengths.map((s) => `<li><i class="fa-solid fa-check" style="color:var(--accent-emerald)"></i> ${s}</li>`).join('')}
              </ul>
            </div>
            <div class="match-factor-box" style="padding:10px;">
              <div class="factor-title gaps" style="font-size:0.75rem;"><i class="fa-solid fa-circle-xmark"></i> Gaps</div>
              <ul class="factor-list" style="font-size:0.75rem;">
                ${displayGaps.map((g) => `<li><i class="fa-solid fa-xmark" style="color:var(--accent-rose)"></i> ${g}</li>`).join('')}
              </ul>
            </div>
          </div>

          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Notes / Comments</h4>
            <textarea id="drawer-comment-text" style="width:100%; min-height:80px; background:rgba(10,14,26,0.5); border:1px solid var(--border-color); color:var(--text-primary); padding:10px; border-radius:6px; font-family:var(--font-body); font-size:0.85rem; resize:vertical; outline:none;" placeholder="Write comments or updates here..." oninput="updateJobComment(${job.id}, this.value)">${job.comment || ''}</textarea>
          </div>

          ${job.enrichmentNote
            ? `
          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-amber); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;"><i class="fa-solid fa-triangle-exclamation"></i> Enrichment Status</h4>
            <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 10px 14px; font-size: 0.85rem; color: #fbbf24;">
              ${job.enrichmentNote}
            </div>
          </div>
          `
            : ''}

          <div style="display:flex; flex-direction:column; gap:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <h4 style="font-size:0.8rem; color:var(--accent-indigo); text-transform:uppercase; letter-spacing:0.05em; margin:0;">Outreach Contacts & Referral Status</h4>
              ${job.status === 'enriched' || job.status === 'enriching'
                ? `
                <button class="btn btn-secondary" style="padding: 3px 10px; font-size: 0.72rem;" onclick="refreshContacts(${job.id}); closeDrawer(null);"><i class="fa-solid fa-arrows-rotate"></i> Refresh Contacts</button>
              `
                : ''}
            </div>
            <div style="display:flex; flex-direction:column; gap:8px;">
              ${buildContactGroupsHtml(job.id, contacts, activeContactIdx)}
            </div>
          </div>

          <div class="outreach-box" style="padding:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <h4 style="font-size:0.85rem; color:var(--accent-indigo); margin:0;">Outreach Message Draft</h4>
            </div>
            ${activeTemplate || (contacts.length === 0 && (job.outreachMessage || job.recruiterOutreachTemplate || job.russianSpeakerOutreachTemplate))
              ? `
              <textarea class="outreach-text" id="drawer-outreach-text" oninput="updateOutreachCounter(); saveOutreachTemplate(${job.id}, this.value)" style="font-size:0.8rem; min-height:100px;">${activeTemplate}</textarea>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                <span id="drawer-char-counter" style="font-size:0.75rem; color:var(--text-muted);">${activeTemplate.length}/200</span>
                <div style="display:flex; gap:8px;">
                  <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="copyDrawerOutreach()"><i class="fa-regular fa-copy"></i> Copy</button>
                  ${job.status === 'enriched'
                    ? `
                    <button class="btn btn-primary" style="padding: 4px 10px; font-size: 0.75rem; background:linear-gradient(135deg, var(--accent-emerald), #059669);" onclick="changeJobStage(${job.id}, 'contacted'); closeDrawer(null);"><i class="fa-solid fa-check"></i> Mark Contacted</button>
                  `
                    : ''}
                </div>
              </div>
            `
              : `
              <p style="font-size:0.75rem; color:var(--text-secondary); text-align:center;">Enrich job listing to source contacts and generate outreach.</p>
              <div style="display:flex; justify-content:center; margin-top:6px;">
                <button class="btn btn-primary" style="padding: 4px 12px; font-size: 0.75rem;" onclick="enrichJob(${job.id}); closeDrawer(null);"><i class="fa-solid fa-wand-magic-sparkles"></i> Enrich Job</button>
              </div>
            `}
          </div>
          <div style="display:flex; justify-content:flex-end; gap:12px; border-top:1px solid var(--border-color); padding-top:16px; margin-top:8px;">
            ${job.status !== 'rejected'
              ? `
              <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.85rem; color: var(--accent-rose); border-color: rgba(244, 63, 94, 0.2);" onclick="changeJobStage(${job.id}, 'rejected'); closeDrawer(null);"><i class="fa-solid fa-ban"></i> Reject Job</button>
            `
              : ''}
            <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.85rem;" onclick="closeDrawer(null)"><i class="fa-solid fa-xmark"></i> Close</button>
          </div>
        </div>
      `;

    overlay.classList.add('active');
  }

  function updateJobComment(id, value) {
    const job = findJob(id);
    if (job) {
      job.comment = value;
      onJobMutated();
    }

    if (commentTimeout) {
      clearTimeout(commentTimeout);
    }
    commentTimeout = setTimeout(() => {
      fetch(`/api/jobs/${id}/comment`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ comment: value }),
      })
        .then((r) => {
          if (!r.ok) throw new Error('HTTP error ' + r.status);
          return r.json();
        })
        .then((updatedJob) => {
          if (job) {
            job.comment = updatedJob.comment;
          }
          addLogLine(`Successfully saved comment for [${job ? job.title : id}] to DB`, 'success');
        })
        .catch((err) => {
          addLogLine(`Failed to save comment: ${err.message}`, 'warning');
        });
    }, 500);
  }

  function saveOutreachTemplate(jobId, template) {
    const job = findJob(jobId);
    if (!job) return;

    const contact = activeContactIdx >= 0 && job.contacts ? job.contacts[activeContactIdx] : null;
    const audience = contact && contact.is_recruiter ? 'recruiter' : 'russian_speaker';
    const normalizedTemplate = normalizeGreeting(template);

    if (audience === 'recruiter') {
      job.recruiterOutreachTemplate = normalizedTemplate;
    } else {
      job.russianSpeakerOutreachTemplate = normalizedTemplate;
    }

    if (templateSaveTimeout) {
      clearTimeout(templateSaveTimeout);
    }
    templateSaveTimeout = setTimeout(() => {
      fetch(`/api/jobs/${jobId}/template`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audience, template: normalizedTemplate }),
      })
        .then((r) => {
          if (!r.ok) throw new Error('HTTP error ' + r.status);
          return r.json();
        })
        .then((updatedJob) => {
          if (job) {
            job.recruiterOutreachTemplate = updatedJob.recruiterOutreachTemplate;
            job.russianSpeakerOutreachTemplate = updatedJob.russianSpeakerOutreachTemplate;
          }
        })
        .catch((err) => {
          addLogLine(`Failed to save outreach template: ${err.message}`, 'warning');
        });
    }, 500);
  }

  async function toggleContacted(jobId, contactIdx, isChecked) {
    const job = findJob(jobId);
    if (!job || !job.contacts || !job.contacts[contactIdx]) return;

    try {
      const resp = await fetch(`/api/jobs/${jobId}/contacts/${contactIdx}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contacted: isChecked }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const updated = await resp.json();

      updateJob(jobId, updated);

      addLogLine(
        `Marked contact ${job.contacts[contactIdx].name} as ${isChecked ? 'CONTACTED' : 'NOT CONTACTED'}.`,
        isChecked ? 'success' : 'warning',
      );
    } catch (err) {
      addLogLine(`Failed to update contact: ${err.message}`, 'error');
    }

    openJobDetailsDrawer(jobId);
    onJobMutated();
  }

  function closeDrawer(e) {
    if (!e || e.target === document.getElementById('kanban-drawer') || e.target.closest('.drawer-close')) {
      document.getElementById('kanban-drawer').classList.remove('active');
    }
  }

  function toggleActivityLog(logId) {
    const panel = document.getElementById(logId);
    const chevron = document.getElementById(logId + '-chevron');
    if (!panel) return;
    const isOpen = panel.style.display !== 'none';
    panel.style.display = isOpen ? 'none' : 'flex';
    if (chevron) chevron.style.transform = isOpen ? '' : 'rotate(90deg)';
  }

  function copyDrawerOutreach() {
    const txt = document.getElementById('drawer-outreach-text');
    if (txt) {
      txt.select();
      document.execCommand('copy');
      addLogLine('Outreach message copied from drawer!', 'success');
    }
  }

  function updateOutreachCounter() {
    const textarea = document.getElementById('drawer-outreach-text');
    const counter = document.getElementById('drawer-char-counter');
    if (!textarea || !counter) return;
    const len = textarea.value.length;
    counter.textContent = `${len}/200`;
    counter.style.color = len > 200 ? 'var(--accent-rose)' : 'var(--text-muted)';
  }

  return {
    closeDrawer,
    copyDrawerOutreach,
    openJobDetailsDrawer,
    saveOutreachTemplate,
    selectActiveContact,
    toggleActivityLog,
    toggleContacted,
    updateJobComment,
    updateOutreachCounter,
  };
}
