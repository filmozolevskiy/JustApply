/** Job details drawer — Active Contact, templates, and outreach UI. */

import { findJob, getJobs, setJobs, updateJob, upsertJob } from './jobStore.js';
import { getBoardJobOrder } from './boardRenderer.js';

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

/** Accepted jobs after enrichment — show Re-classify / Load More even with zero matching contacts. */
export function hasContactSampleActions(job, contacts = job.contacts || []) {
  if (job.status !== 'accepted') return false;
  return (
    contacts.length > 0 ||
    Boolean(job.enrichmentNote) ||
    Boolean(job.outreachMessage) ||
    Boolean(job.recruiterOutreachTemplate) ||
    Boolean(job.russianSpeakerOutreachTemplate)
  );
}

function activityLogEntryMeta(message) {
  if (message.startsWith('Enrichment failed ·')) {
    return { color: '#fbbf24', icon: 'fa-triangle-exclamation' };
  }
  if (message.startsWith('Re-classified ·')) {
    return { color: '#22d3ee', icon: 'fa-circle-info' };
  }
  return { color: 'var(--text-secondary)', icon: null };
}

export function hasContactedElsewhere(contact) {
  return Boolean(contact?.contactedElsewhere?.jobId);
}

export function pickDefaultActiveContact(contacts) {
  if (!contacts.length) return -1;
  const withoutElsewhere = contacts.findIndex((c) => !c.contacted && !hasContactedElsewhere(c));
  if (withoutElsewhere !== -1) return withoutElsewhere;
  const uncontacted = contacts.findIndex((c) => !c.contacted);
  if (uncontacted !== -1) return uncontacted;
  return 0;
}

function contactedElsewhereBadgeHtml(contact) {
  if (contact.contacted || !hasContactedElsewhere(contact)) return '';
  const { jobId, company, title } = contact.contactedElsewhere;
  const label = `${company} — ${title}`;
  return `<button type="button" class="contacted-elsewhere-badge" onclick="openContactedElsewhereJob(${jobId}, event)" title="Already contacted for another role — click to review">${label}</button>`;
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
                    ${contactedElsewhereBadgeHtml(contact)}
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

export function createDrawerController({
  onJobMutated,
  addLogLine,
  getActiveReclassifyJobIds = () => [],
  getActiveLoadMoreJobId = () => null,
  getBoardFilters = () => ({}),
}) {
  let activeContactIdx = -1;
  let commentTimeout = null;
  let templateSaveTimeout = null;
  let drawerJobId = null;

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

  function getDrawerJobNeighbors() {
    if (drawerJobId == null) {
      return { prevId: null, nextId: null, index: -1, total: 0 };
    }
    const ordered = getBoardJobOrder(getJobs(), getBoardFilters());
    const index = ordered.findIndex((j) => j.id === drawerJobId);
    if (index === -1) {
      return { prevId: null, nextId: null, index: -1, total: ordered.length };
    }
    return {
      prevId: index > 0 ? ordered[index - 1].id : null,
      nextId: index < ordered.length - 1 ? ordered[index + 1].id : null,
      index,
      total: ordered.length,
    };
  }

  function updateDrawerNav() {
    const { prevId, nextId } = getDrawerJobNeighbors();
    const prevBtn = document.getElementById('drawer-nav-prev');
    const nextBtn = document.getElementById('drawer-nav-next');
    if (prevBtn) {
      prevBtn.disabled = prevId == null;
    }
    if (nextBtn) {
      nextBtn.disabled = nextId == null;
    }
  }

  function navigateDrawerJob(delta) {
    const { prevId, nextId } = getDrawerJobNeighbors();
    const targetId = delta < 0 ? prevId : nextId;
    if (targetId == null) return;
    openJobDetailsDrawer(targetId);
    document.querySelector('.drawer-content')?.scrollTo(0, 0);
  }

  function openJobDetailsDrawer(id) {
    const job = findJob(id);
    if (!job) return;

    drawerJobId = id;

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
    activeContactIdx = pickDefaultActiveContact(contacts);

    const rawActiveTemplate = activeContactIdx >= 0 ? getActiveTemplate(job, activeContactIdx) : '';
    const defaultContact = activeContactIdx >= 0 ? contacts[activeContactIdx] : null;
    const defaultFirstName = defaultContact ? defaultContact.name.split(' ')[0] : '';
    const activeTemplate = defaultFirstName
      ? applyGreetingName(rawActiveTemplate, defaultFirstName)
      : rawActiveTemplate;

    const isReclassifying = getActiveReclassifyJobIds().includes(job.id);
    const isLoadingMore = getActiveLoadMoreJobId() === job.id;
    const contactActionInProgress = isReclassifying || isLoadingMore;
    const reclassifyBusy = isReclassifying;

    const hasPostingLink =
      job.link && job.link.trim() && job.link !== '#' && job.link !== 'undefined';

    body.innerHTML = `
        <div class="drawer-header">
          <h2 class="drawer-header-title">${job.title}</h2>
          <div class="drawer-header-actions">
            ${hasPostingLink ? `
              <a href="${job.link}" target="_blank" class="drawer-header-linkedin" title="View LinkedIn Posting"><i class="fa-brands fa-linkedin"></i></a>
            ` : ''}
            <span class="match-pill ${matchClass}" style="font-size:1.1rem; padding: 4px 10px;">${job.matchScore}% Match</span>
          </div>
        </div>

        ${job.isRecruiter ? `
          <div style="background: linear-gradient(90deg, rgba(244, 63, 94, 0.1) 0%, rgba(245, 158, 11, 0.1) 100%); border: 1px solid rgba(244, 63, 94, 0.25); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 0.85rem; color: #f43f5e; display: flex; align-items: center; gap: 10px;">
            <i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; font-size:1.15rem; flex-shrink:0;"></i>
            <span><strong>Recruiting / Staffing Agency Warning:</strong> This job posting was published by a recruitment or staffing agency, not directly by the employer. The match score has been penalized by 15 points.</span>
          </div>
        ` : ''}

        ${job.unclassified ? `
          <div style="margin-bottom: 16px;">
            <span style="font-size:0.7rem; background:rgba(245, 158, 11, 0.15); color:#f59e0b; border:1px solid rgba(245, 158, 11, 0.3); padding:3px 8px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em; cursor:help;" title="Remote type and seniority were not classified by the Resume Matcher; scraper values were used instead.">Unclassified</span>
          </div>
        ` : ''}

        <div style="display:flex; flex-direction:column; gap:14px;">
          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Job Info</h4>
            <div class="drawer-job-info-grid">
              <div>Status: <span class="status-badge status-${job.status}" style="font-size:0.65rem; padding: 2px 6px;">${job.status}</span></div>
              <div>Seniority: <span style="text-transform:capitalize;">${job.seniority}</span></div>
              <div>Company: <strong>${job.company}</strong></div>
              <div>Location: ${job.location}</div>
              <div>Remote Policy: <span style="text-transform:capitalize;">${job.remoteType}</span></div>
              <div>Salary: <span class="drawer-salary">${job.salary || 'Not specified'}</span></div>
              <div class="drawer-job-info-full">Resume Profile: <code>${job.resumeUsed}</code></div>
            </div>
          </div>

          ${job.activityLog && job.activityLog.length > 0
            ? (() => {
                const log = job.activityLog;
                const latest = log[log.length - 1];
                const latestMeta = activityLogEntryMeta(latest.message);
                const logId = 'activity-log-' + job.id;
                return `
          <div>
            <button onclick="toggleActivityLog('${logId}')" style="background:none; border:none; cursor:pointer; display:flex; align-items:center; gap:6px; padding:0; width:100%; text-align:left; margin-bottom:0;">
              <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin:0;">Job Activity Log</h4>
              <i id="${logId}-chevron" class="fa-solid fa-chevron-right" style="font-size:0.65rem; color:var(--text-muted); transition:transform 0.2s;"></i>
              <span style="font-size:0.78rem; color:${latestMeta.color}; font-weight:400; text-transform:none; letter-spacing:0; margin-left:4px;">${latestMeta.icon ? `<i class="fa-solid ${latestMeta.icon}"></i> ` : ''}${latest.message}</span>
            </button>
            <div id="${logId}" style="display:none; margin-top:8px; border-left:2px solid rgba(6,182,212,0.2); padding-left:10px; flex-direction:column; gap:4px;">
              ${log
                .map((e) => {
                  const meta = activityLogEntryMeta(e.message);
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
                  <span style="color:${meta.color};">${meta.icon ? `<i class="fa-solid ${meta.icon}"></i> ` : ''}${e.message}</span>
                </div>`;
                })
                .join('')}
            </div>
          </div>`;
              })()
            : ''}

          <div>
            <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Description</h4>
            <div class="detail-description">${job.description}</div>
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

          <div style="display:flex; flex-direction:column; gap:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <h4 style="font-size:0.8rem; color:var(--accent-indigo); text-transform:uppercase; letter-spacing:0.05em; margin:0;">Outreach Contacts & Referral Status</h4>
            </div>
            ${isReclassifying
              ? `
            <div style="display:flex; align-items:center; gap:8px; font-size:0.8rem; color:var(--accent-cyan); padding:8px 12px; background:rgba(6,182,212,0.08); border:1px solid rgba(6,182,212,0.2); border-radius:6px;">
              <i class="fa-solid fa-spinner fa-spin"></i> Re-classifying contacts…
            </div>
            `
              : ''}
            ${isLoadingMore
              ? `
            <div style="display:flex; align-items:center; gap:8px; font-size:0.8rem; color:#818cf8; padding:8px 12px; background:rgba(99,102,241,0.08); border:1px solid rgba(99,102,241,0.2); border-radius:6px;">
              <i class="fa-solid fa-spinner fa-spin"></i> Loading more contacts…
            </div>
            `
              : ''}
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
              <textarea class="outreach-text" id="drawer-outreach-text" oninput="updateOutreachCounter(); saveOutreachTemplate(${job.id}, this.value)" style="font-size:0.8rem;">${activeTemplate}</textarea>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                <span id="drawer-char-counter" style="font-size:0.75rem; color:var(--text-muted);">${activeTemplate.length}/200</span>
                <div style="display:flex; gap:8px;">
                  <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="copyDrawerOutreach()"><i class="fa-regular fa-copy"></i> Copy</button>
                  ${job.status === 'accepted'
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
            ${job.status === 'accepted' && job.companyUrl
              ? `
              <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.85rem; color: var(--accent-indigo); border-color: rgba(99,102,241,0.2);${contactActionInProgress ? ' opacity:0.55; pointer-events:none;' : ''}" onclick="loadMoreContacts(${job.id})"${contactActionInProgress ? ' disabled' : ''}><i class="fa-solid ${isLoadingMore ? 'fa-spinner fa-spin' : 'fa-users-line'}"></i> ${isLoadingMore ? 'Loading contacts…' : 'Load More Contacts'}</button>
              `
              : ''}
            ${job.status === 'accepted'
              ? `
              <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.85rem; color: var(--accent-cyan); border-color: rgba(6,182,212,0.2);${reclassifyBusy || isLoadingMore ? ' opacity:0.55; pointer-events:none;' : ''}" onclick="reclassifyJob(${job.id})"${reclassifyBusy || isLoadingMore ? ' disabled' : ''}><i class="fa-solid ${isReclassifying ? 'fa-spinner fa-spin' : 'fa-rotate'}"></i> ${isReclassifying ? 'Re-classifying…' : 'Re-classify'}</button>
              `
              : ''}
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
    updateDrawerNav();
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

  async function reloadJobsFromServer() {
    const archivedFilter =
      document.getElementById('board-filter-archived')?.value ||
      localStorage.getItem('boardFilterArchived') ||
      'active';
    const resp = await fetch(`/api/jobs?archived=${archivedFilter}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    setJobs(Array.isArray(data) ? data : []);
  }

  async function openContactedElsewhereJob(sourceJobId, event) {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    if (!findJob(sourceJobId)) {
      try {
        const resp = await fetch(`/api/jobs/${sourceJobId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        upsertJob(await resp.json());
      } catch (err) {
        addLogLine(`Could not open job #${sourceJobId}: ${err.message}`, 'error');
        return;
      }
    }
    openJobDetailsDrawer(sourceJobId);
    onJobMutated();
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

      try {
        await reloadJobsFromServer();
      } catch (reloadErr) {
        addLogLine(`Contact updated but refresh failed: ${reloadErr.message}`, 'warning');
      }

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
    if (
      !e ||
      e.target === document.getElementById('kanban-drawer') ||
      e.target.closest('.drawer-close')
    ) {
      document.getElementById('kanban-drawer').classList.remove('active');
      drawerJobId = null;
    }
  }

  function refreshDrawerIfOpen(id) {
    const overlay = document.getElementById('kanban-drawer');
    if (overlay?.classList.contains('active')) {
      openJobDetailsDrawer(id);
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

  document.addEventListener('keydown', (e) => {
    const overlay = document.getElementById('kanban-drawer');
    if (!overlay?.classList.contains('active')) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    e.preventDefault();
    navigateDrawerJob(e.key === 'ArrowLeft' ? -1 : 1);
  });

  return {
    closeDrawer,
    copyDrawerOutreach,
    navigateDrawerJob,
    openContactedElsewhereJob,
    openJobDetailsDrawer,
    refreshDrawerIfOpen,
    saveOutreachTemplate,
    selectActiveContact,
    toggleActivityLog,
    toggleContacted,
    updateDrawerNav,
    updateJobComment,
    updateOutreachCounter,
  };
}
