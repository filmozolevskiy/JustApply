/** Kanban board filtering, sorting, and DOM rendering. */

export const LANES = ['scraped', 'matched', 'accepted', 'applied', 'interviewing', 'rejected'];

export const BOARD_SEARCH_FIELD_KEYS = ['title', 'company', 'location', 'description'];

export function parseBoardSearchTerms(query) {
  if (!query || typeof query !== 'string') {
    return [];
  }
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function buildBoardSearchJobHaystack(job) {
  return BOARD_SEARCH_FIELD_KEYS.map((key) => String(job[key] || '').toLowerCase()).join('\n');
}

function buildBoardSearchContactHaystack(job) {
  const contacts = Array.isArray(job.contacts) ? job.contacts : [];
  return contacts.map((contact) => String(contact?.name || '').toLowerCase()).join('\n');
}

function haystackMatchesBoardSearchTerms(haystack, terms) {
  return terms.every((term) => haystack.includes(term));
}

export function jobContactsMatchBoardSearch(job, query) {
  const terms = parseBoardSearchTerms(query);
  if (terms.length === 0) {
    return true;
  }
  return haystackMatchesBoardSearchTerms(buildBoardSearchContactHaystack(job), terms);
}

export function jobMatchesBoardSearch(job, query) {
  const terms = parseBoardSearchTerms(query);
  if (terms.length === 0) {
    return true;
  }

  const haystack = [buildBoardSearchJobHaystack(job), buildBoardSearchContactHaystack(job)]
    .filter(Boolean)
    .join('\n');
  return haystackMatchesBoardSearchTerms(haystack, terms);
}

export function getCompanySizeCategory(sizeStr) {
  if (!sizeStr) return 'unknown';
  const sizeLower = sizeStr.toLowerCase().trim();

  const cleanStr = sizeStr.replace(/,/g, '');
  const numbers = cleanStr.match(/\d+/g);
  if (numbers) {
    const maxVal = Math.max(...numbers.map(Number));
    if (maxVal <= 50) return 'small';
    if (maxVal <= 500) return 'medium';
    return 'large';
  }

  if (sizeLower.includes('small') || sizeLower.includes('1-50') || sizeLower.includes('10-50')) {
    return 'small';
  }
  if (
    sizeLower.includes('medium') ||
    sizeLower.includes('50-500') ||
    sizeLower.includes('100-500') ||
    sizeLower.includes('200-500')
  ) {
    return 'medium';
  }
  return 'large';
}

export function filterJobs(jobs, filters) {
  const remoteFilter = filters.remote || 'all';
  const sizeFilter = filters.size || 'all';
  const recruiterFilter = filters.recruiter || 'all';
  const searchQuery = filters.search ?? '';

  return jobs.filter((job) => {
    if (!jobMatchesBoardSearch(job, searchQuery)) {
      return false;
    }

    if (remoteFilter !== 'all') {
      let normalizedRemote = (job.remoteType || '').toLowerCase().trim();
      if (normalizedRemote === 'in office') normalizedRemote = 'in_office';
      if (normalizedRemote !== remoteFilter) {
        return false;
      }
    }

    if (sizeFilter !== 'all') {
      const sizeCat = getCompanySizeCategory(job.size);
      if (sizeCat !== sizeFilter) {
        return false;
      }
    }

    if (recruiterFilter === 'exclude') {
      if (job.isRecruiter) {
        return false;
      }
    } else if (recruiterFilter === 'only') {
      if (!job.isRecruiter) {
        return false;
      }
    }

    return true;
  });
}

export function sortJobs(jobs, sortBy) {
  const sorted = [...jobs];
  sorted.sort((a, b) => {
    if (sortBy === 'match_desc') {
      return (b.matchScore || 0) - (a.matchScore || 0);
    }
    if (sortBy === 'match_asc') {
      return (a.matchScore || 0) - (b.matchScore || 0);
    }
    if (sortBy === 'novelty_desc') {
      if (a.date && b.date) {
        if (a.date !== b.date) {
          return b.date.localeCompare(a.date);
        }
      }
      return (b.id || 0) - (a.id || 0);
    }
    if (sortBy === 'novelty_asc') {
      if (a.date && b.date) {
        if (a.date !== b.date) {
          return a.date.localeCompare(b.date);
        }
      }
      return (a.id || 0) - (b.id || 0);
    }
    return 0;
  });
  return sorted;
}

export function getBoardFiltersFromDom() {
  return {
    remote: document.getElementById('board-filter-remote')?.value || 'all',
    size: document.getElementById('board-filter-size')?.value || 'all',
    recruiter: document.getElementById('board-filter-recruiter')?.value || 'all',
    search: document.getElementById('board-filter-search')?.value || '',
    sortBy: document.getElementById('board-sort-by')?.value || 'match_desc',
  };
}

/** Visible jobs in Kanban display order: lane left-to-right, sorted within each lane. */
export function getBoardJobOrder(jobs, filters = {}) {
  const filtered = sortJobs(filterJobs(jobs, filters), filters.sortBy || 'match_desc');
  const ordered = [];
  for (const lane of LANES) {
    for (const job of filtered) {
      if (job.status === lane) {
        ordered.push(job);
      }
    }
  }
  return ordered;
}

export function cardEnrichingBadge(jobId, enrichingJobId) {
  if (enrichingJobId != null && jobId === enrichingJobId) {
    return `<span style="font-size:0.6rem; background:rgba(99,102,241,0.15); color:#818cf8; border:1px solid rgba(99,102,241,0.3); padding:1px 5px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;"><i class="fa-solid fa-spinner fa-spin"></i> Enriching…</span>`;
  }
  return '';
}

export function cardLoadMoreBadge(jobId, loadMoreJobId) {
  if (loadMoreJobId != null && jobId === loadMoreJobId) {
    return `<span style="font-size:0.6rem; background:rgba(99,102,241,0.15); color:#818cf8; border:1px solid rgba(99,102,241,0.3); padding:1px 5px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;"><i class="fa-solid fa-spinner fa-spin"></i> Loading contacts…</span>`;
  }
  return '';
}

export function cardReclassifyBadge(jobId, reclassifyJobIds) {
  if (Array.isArray(reclassifyJobIds) && reclassifyJobIds.includes(jobId)) {
    return `<span style="font-size:0.6rem; background:rgba(6,182,212,0.15); color:#22d3ee; border:1px solid rgba(6,182,212,0.3); padding:1px 5px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;"><i class="fa-solid fa-spinner fa-spin"></i> Re-classifying…</span>`;
  }
  return '';
}

export function getKanbanCardMovementButtons(job) {
  if (job.archived) {
    return `<button class="kanban-action-btn unarchive-btn hover-reject" onclick="archiveJob(${job.id})" title="Un-archive Job"><i class="fa-solid fa-box-open"></i></button>`;
  }
  if (job.status === 'rejected') {
    return `<button class="kanban-action-btn archive-btn hover-reject" onclick="archiveJob(${job.id})" title="Archive Job"><i class="fa-solid fa-box-archive"></i></button>`;
  }
  return `<button class="kanban-action-btn reject-btn hover-reject" onclick="moveJobStage(${job.id}, 'rejected')" title="Reject Job"><i class="fa-solid fa-ban"></i></button>`;
}

export function renderBoard(jobs, filters = {}) {
  const filteredJobs = sortJobs(filterJobs(jobs, filters), filters.sortBy || 'match_desc');
  const enrichingJobId = filters.enrichingJobId ?? null;
  const loadMoreJobId = filters.loadMoreJobId ?? null;
  const reclassifyJobIds = filters.reclassifyJobIds ?? [];

  LANES.forEach((lane) => {
    const laneEl = document.getElementById(`lane-${lane}`);
    if (!laneEl) return;
    laneEl.innerHTML = '';

    const jobsInLane = filteredJobs.filter((j) => j.status === lane);
    const countEl = document.getElementById(`count-${lane}`);
    if (countEl) countEl.textContent = jobsInLane.length;

    jobsInLane.forEach((job) => {
      const card = document.createElement('div');
      card.className = 'kanban-card' + (job.archived ? ' kanban-card--archived' : '');
      card.setAttribute('onclick', `openJobDetailsDrawer(${job.id})`);
      card.setAttribute('draggable', 'true');
      card.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', String(job.id));
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(() => card.classList.add('dragging'), 0);
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        document.querySelectorAll('.kanban-column.drag-over').forEach((c) => c.classList.remove('drag-over'));
      });

      let matchClass = 'match-low';
      if (job.matchScore >= 85) matchClass = 'match-high';
      else if (job.matchScore >= 70) matchClass = 'match-mid';

      const badgeParts = [
        job.archived ? `<span class="archived-badge">Archived</span>` : '',
        job.unclassified
          ? `<span style="font-size:0.6rem; background:rgba(245, 158, 11, 0.15); color:#f59e0b; border:1px solid rgba(245, 158, 11, 0.3); padding:1px 5px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;" title="Remote type and seniority were not classified by the Resume Matcher; scraper values were used instead.">Unclassified</span>`
          : '',
        job.isRecruiter
          ? `<span style="font-size:0.6rem; background:rgba(239, 68, 68, 0.15); color:#ef4444; border:1px solid rgba(239, 68, 68, 0.3); padding:1px 5px; border-radius:4px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;">Recruiter</span>`
          : '',
        cardEnrichingBadge(job.id, enrichingJobId),
        cardLoadMoreBadge(job.id, loadMoreJobId),
        cardReclassifyBadge(job.id, reclassifyJobIds),
      ].filter(Boolean);
      const badgesHtml = badgeParts.length
        ? `<div class="kanban-card-badges">${badgeParts.join('')}</div>`
        : '';

      card.innerHTML = `
            <div class="kanban-card-header">
              <div class="kanban-card-title">
                ${job.title || 'Incomplete Job'}
                ${job.link && job.link.trim() && job.link !== '#' && job.link !== 'undefined' ? `
                  <a href="${job.link}" target="_blank" onclick="event.stopPropagation()" class="kanban-card-linkedin" title="View LinkedIn Posting" style="margin-left: 4px; vertical-align: middle;"><i class="fa-brands fa-linkedin"></i></a>
                ` : ''}
              </div>
              <div class="kanban-card-header-actions">
                <span class="match-pill ${matchClass}">${job.matchScore}%</span>
              </div>
            </div>
            <div class="kanban-card-company-block">
              <span class="kanban-card-company-name"><i class="fa-regular fa-building"></i> ${job.company}</span>
              ${badgesHtml}
            </div>
            <div class="kanban-card-meta-block">
              <div class="kanban-card-meta-primary">
                <span><i class="fa-solid fa-location-dot"></i> ${job.location}</span>
                <span class="kanban-card-meta-remote">${job.remoteType}</span>
              </div>
              ${job.salary ? `<div class="kanban-card-meta-salary"><i class="fa-solid fa-dollar-sign"></i> ${job.salary}</div>` : ''}
            </div>
            ${job.comment ? `
              <div style="font-size: 0.72rem; color: #a78bfa; font-style: italic; background: rgba(139, 92, 246, 0.08); padding: 4px 8px; border-radius: 4px; margin-top: 4px; border-left: 2px solid #a78bfa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                <i class="fa-regular fa-comment-dots"></i> ${job.comment}
              </div>
            ` : ''}
            <div class="kanban-card-footer">
              <span style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${job.resumeUsed}</span>
              <div class="kanban-card-actions" onclick="event.stopPropagation()">
                ${getKanbanCardMovementButtons(job)}
              </div>
            </div>
          `;
      laneEl.appendChild(card);
    });
  });
}
