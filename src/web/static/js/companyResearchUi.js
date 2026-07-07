/** Company Research drawer section — Variant A (Metrics grid). */

export function companyResearchAllowed(status, archived = false) {
  if (archived) return false;
  return ['matched', 'accepted', 'applied', 'interviewing'].includes(status);
}

function formatSalary(salary) {
  if (!salary || salary.medianBaseSalary == null) return null;
  const n = Number(salary.medianBaseSalary).toLocaleString();
  return `$${n} ${salary.currency || 'USD'}${salary.sampleSize ? ` (${salary.sampleSize} reports)` : ''}`;
}

function glassdoorOverviewUrl(companyId, matchedName) {
  const slug = String(matchedName || 'company')
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-');
  return `https://www.glassdoor.com/Overview/Working-at-${slug}-EI_IE${companyId}.htm`;
}

function glassdoorBadgeHtml() {
  return `<svg class="drawer-glassdoor-icon" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
    <rect width="20" height="20" rx="4" fill="currentColor"/>
    <text x="10" y="14.5" text-anchor="middle" fill="#fff" font-size="11" font-weight="700" font-family="Arial, Helvetica, sans-serif">G</text>
  </svg>`;
}

function buildDrawerGlassdoorLinkHtml(companyId, matchedName) {
  if (!companyId || !matchedName) return '';
  const url = glassdoorOverviewUrl(companyId, matchedName);
  return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="drawer-company-glassdoor" title="View ${matchedName} on Glassdoor">${glassdoorBadgeHtml()}</a>`;
}

function sectionHeaderHtml({ data = null, showActions = false, jobId = null } = {}) {
  const link = data ? buildDrawerGlassdoorLinkHtml(data.glassdoorCompanyId, data.matchedName) : '';
  const actions =
    showActions && jobId
      ? `<div class="cr-actions">
      <button type="button" class="cr-btn-ghost" onclick="researchCompany(${jobId})"><i class="fa-solid fa-rotate"></i> Refresh</button>
    </div>`
      : '';
  return `
    <div class="cr-header">
      <div class="cr-title-row">
        <h4 class="cr-title">Glassdoor Company Research</h4>
        ${link}
      </div>
      ${actions}
    </div>`;
}

function emptyBlockHtml(jobId) {
  return `
    <div class="cr-empty-cta">
      <p>Glassdoor employer intel — company rating, recommend %, salary band for your role, and interview process notes.</p>
      <button type="button" class="btn btn-cyan" onclick="researchCompany(${jobId})"><i class="fa-solid fa-magnifying-glass-chart"></i> Research company</button>
    </div>`;
}

function loadingHtml() {
  return `
    <div class="cr-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Researching employer on Glassdoor…</span>
    </div>`;
}

function researchedHtml(data, jobId) {
  const salaryStr = formatSalary(data.salary);
  const title = data.glassdoorJobTitle || 'Role';
  const rating = data.rating != null ? data.rating : 'n/a';
  const reviewCount =
    data.reviewCount != null ? Number(data.reviewCount).toLocaleString() : 'n/a';
  const recommend = data.recommendPercent != null ? `${data.recommendPercent}%` : 'n/a';
  const size = data.companySize || 'n/a';
  const interviews = data.interviews || [];
  const matchedLine = data.matchedName
    ? `<div class="cr-a-row" style="font-size:0.78rem; color:var(--text-muted);">Matched employer: <strong style="color:var(--text-secondary);">${data.matchedName}</strong></div>`
    : '';

  return `
    ${sectionHeaderHtml({ data, showActions: true, jobId })}
    ${matchedLine}
    <div class="cr-a-metrics">
      <div class="cr-a-metric">
        <div class="cr-a-metric-label">Size</div>
        <div class="cr-a-metric-value">${size}</div>
      </div>
      <div class="cr-a-metric">
        <div class="cr-a-metric-label">Rating</div>
        <div class="cr-a-metric-value">${rating} <span style="color:var(--accent-amber); font-size:0.85rem;">★</span></div>
        <div class="cr-a-metric-sub">${reviewCount} reviews</div>
      </div>
      <div class="cr-a-metric">
        <div class="cr-a-metric-label">Recommend</div>
        <div class="cr-a-metric-value">${recommend}</div>
        <div class="cr-a-metric-sub">would recommend</div>
      </div>
    </div>
    <div class="cr-a-row">Base salary (${title}): ${salaryStr ? `<strong style="color:#10b981">${salaryStr}</strong>` : '<span class="cr-na">n/a</span>'}</div>
    ${
      interviews.length
        ? interviews
            .map(
              (iv) => `
      <div class="cr-a-interview">
        <strong style="color:var(--text-primary); font-size:0.78rem;">${iv.difficulty || '—'} · ${iv.outcome || '—'}</strong><br>
        ${iv.processSummary || ''}
      </div>`,
            )
            .join('')
        : '<div class="cr-a-interview"><span class="cr-na">n/a — no interview reports for this title on Glassdoor</span></div>'
    }`;
}

export function buildCompanyResearchSectionHtml(job, { isResearching = false } = {}) {
  if (!companyResearchAllowed(job.status, job.archived)) {
    return '';
  }

  if (isResearching) {
    return `<section class="cr-section">${sectionHeaderHtml()}${loadingHtml()}</section>`;
  }

  const data = job.companyResearch;
  if (!data || !data.glassdoorCompanyId) {
    return `<section class="cr-section">${sectionHeaderHtml()}${emptyBlockHtml(job.id)}</section>`;
  }

  return `<section class="cr-section">${researchedHtml(data, job.id)}</section>`;
}
