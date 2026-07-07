/** PROTOTYPE — Company Research drawer UI variants. Delete when variant is chosen. */

const VARIANTS = [
  { key: 'A', name: 'Metrics grid' },
  { key: 'B', name: 'Scorecard hero' },
  { key: 'C', name: 'Dossier report' },
];

const STATES = ['empty', 'full', 'sparse', 'loading'];

const MOCK_JOB = {
  title: 'Senior QA Engineer (Hybrid)',
  company: 'FlightHub',
  companyUrl: 'https://www.linkedin.com/company/flighthub/',
  status: 'matched',
  seniority: 'mid',
  location: 'Montreal, QC',
  remoteType: 'hybrid',
  salary: 'Not specified',
  resumeUsed: 'qa.md',
  matchScore: 78,
  size: '51-200',
};

const MOCK_RESEARCH = {
  full: {
    glassdoorCompanyId: '882104',
    matchedName: 'TechVentures Inc.',
    companySize: '1,001 to 5,000 Employees',
    rating: 4.1,
    reviewCount: 1247,
    recommendPercent: 78,
    glassdoorJobTitle: 'QA Engineer',
    salary: { medianBaseSalary: 85000, currency: 'USD', sampleSize: 42 },
    interviews: [
      {
        jobTitle: 'QA Engineer',
        difficulty: 'Average',
        outcome: 'Accepted offer',
        processSummary:
          'Recruiter phone screen (30 min) → technical interview with QA lead (SQL + test design) → final with engineering manager. Whole process took about 2.5 weeks.',
      },
      {
        jobTitle: 'QA Engineer',
        difficulty: 'Easy',
        outcome: 'No offer',
        processSummary: 'Two rounds only — HR screen and a take-home automation exercise reviewed in a 45-minute follow-up.',
      },
    ],
  },
  sparse: {
    glassdoorCompanyId: '961018',
    matchedName: 'FlightHub',
    companySize: '51 to 200 Employees',
    rating: 2.8,
    reviewCount: 246,
    recommendPercent: 40,
    glassdoorJobTitle: 'QA Engineer',
    salary: null,
    interviews: [],
  },
};

function ratingClass(rating) {
  if (rating == null) return '';
  if (rating >= 3.8) return 'high';
  if (rating < 3.2) return 'low';
  return '';
}

function formatSalary(salary) {
  if (!salary || salary.medianBaseSalary == null) return null;
  const n = Number(salary.medianBaseSalary).toLocaleString();
  return `$${n} ${salary.currency || 'USD'}${salary.sampleSize ? ` (${salary.sampleSize} reports)` : ''}`;
}

function buildJobInfoHtml(job) {
  const linkedin =
    job.companyUrl && job.companyUrl.trim()
      ? ` <a href="${job.companyUrl}" target="_blank" rel="noopener" class="drawer-company-linkedin" title="LinkedIn"><i class="fa-brands fa-linkedin"></i></a>`
      : '';
  return `
    <div>
      <h4 style="font-size:0.8rem; color:var(--accent-cyan); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">Job Info</h4>
      <div class="drawer-job-info-grid">
        <div>Status: <span class="status-badge status-${job.status}" style="font-size:0.65rem; padding: 2px 6px;">${job.status}</span></div>
        <div>Seniority: <span style="text-transform:capitalize;">${job.seniority}</span></div>
        <div>Company: <strong>${job.company}</strong>${linkedin}</div>
        <div>Location: ${job.location}</div>
        <div>Remote Policy: <span style="text-transform:capitalize;">${job.remoteType}</span></div>
        <div>Salary: <span class="drawer-salary">${job.salary}</span></div>
        <div class="drawer-job-info-full">Resume Profile: <code>${job.resumeUsed}</code></div>
      </div>
    </div>`;
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

function sectionHeaderHtml({ data = null, showActions = false } = {}) {
  const link = data ? buildDrawerGlassdoorLinkHtml(data.glassdoorCompanyId, data.matchedName) : '';
  return `
    <div class="cr-header">
      <div class="cr-title-row">
        <h4 class="cr-title">Glassdoor Company Research</h4>
        ${link}
      </div>
      ${showActions ? actionButtonsHtml() : ''}
    </div>`;
}

function actionButtonsHtml() {
  return `
    <div class="cr-actions">
      <button type="button" class="cr-btn-ghost" data-demo="refresh"><i class="fa-solid fa-rotate"></i> Refresh</button>
      <button type="button" class="cr-btn-ghost warn" data-demo="wrong-company"><i class="fa-solid fa-building-circle-xmark"></i> Wrong company?</button>
    </div>`;
}

function emptyBlockHtml(variant) {
  if (variant === 'B') {
    return `
      <div class="cr-b-empty">
        <div class="cr-b-empty-icon"><i class="fa-solid fa-chart-simple"></i></div>
        <p style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:14px;">No Glassdoor research yet for this employer.</p>
        <button type="button" class="btn btn-cyan" data-demo="research"><i class="fa-solid fa-magnifying-glass-chart"></i> Research company</button>
        <p style="font-size:0.75rem; color:var(--text-muted); margin-top:12px;">Rating, recommend %, salary band, interview notes</p>
      </div>`;
  }
  return `
    <div class="cr-empty-cta">
      <p>Glassdoor employer intel — company rating, recommend %, salary band for your role, and interview process notes.</p>
      <button type="button" class="btn btn-cyan" data-demo="research"><i class="fa-solid fa-magnifying-glass-chart"></i> Research company</button>
    </div>`;
}

function loadingHtml() {
  return `
    <div class="cr-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Researching employer on Glassdoor…</span>
    </div>`;
}

function renderVariantA(state, data) {
  if (state === 'empty') {
    return `<section class="cr-section">${sectionHeaderHtml()}${emptyBlockHtml('A')}</section>`;
  }
  if (state === 'loading') {
    return `<section class="cr-section">${sectionHeaderHtml()}${loadingHtml()}</section>`;
  }

  const salaryStr = formatSalary(data.salary);
  const title = data.glassdoorJobTitle || 'QA Engineer';

  return `
    <section class="cr-section">
      ${sectionHeaderHtml({ data, showActions: true })}
      <div class="cr-a-metrics">
        <div class="cr-a-metric">
          <div class="cr-a-metric-label">Size</div>
          <div class="cr-a-metric-value">${data.companySize}</div>
        </div>
        <div class="cr-a-metric">
          <div class="cr-a-metric-label">Rating</div>
          <div class="cr-a-metric-value">${data.rating} <span style="color:var(--accent-amber); font-size:0.85rem;">★</span></div>
          <div class="cr-a-metric-sub">${data.reviewCount.toLocaleString()} reviews</div>
        </div>
        <div class="cr-a-metric">
          <div class="cr-a-metric-label">Recommend</div>
          <div class="cr-a-metric-value">${data.recommendPercent}%</div>
          <div class="cr-a-metric-sub">would recommend</div>
        </div>
      </div>
      <div class="cr-a-row">Base salary (${title}): ${salaryStr ? `<strong style="color:#10b981">${salaryStr}</strong>` : '<span class="cr-na">n/a</span>'}</div>
      ${
        data.interviews.length
          ? data.interviews
              .map(
                (iv) => `
        <div class="cr-a-interview">
          <strong style="color:var(--text-primary); font-size:0.78rem;">${iv.difficulty || '—'} · ${iv.outcome || '—'}</strong><br>
          ${iv.processSummary}
        </div>`,
              )
              .join('')
          : '<div class="cr-a-interview"><span class="cr-na">n/a — no interview reports for this title on Glassdoor</span></div>'
      }
    </section>`;
}

function renderVariantB(state, data) {
  if (state === 'empty') {
    return `
      <section class="cr-section">
        ${sectionHeaderHtml()}
        ${emptyBlockHtml('B')}
      </section>`;
  }
  if (state === 'loading') {
    return `
      <section class="cr-section">
        ${sectionHeaderHtml()}
        ${loadingHtml()}
      </section>`;
  }

  const salaryStr = formatSalary(data.salary);
  const title = data.glassdoorJobTitle || 'QA Engineer';
  const ringClass = ratingClass(data.rating);

  return `
    <section class="cr-section">
      ${sectionHeaderHtml({ data, showActions: true })}
      <div class="cr-b-scorecard">
        <div class="cr-b-rating-ring ${ringClass}">
          <div class="cr-b-rating-num">${data.rating}</div>
          <div class="cr-b-rating-label">of 5</div>
        </div>
        <div class="cr-b-stats">
          <div class="cr-b-stat"><strong>${data.reviewCount.toLocaleString()}</strong> Glassdoor reviews</div>
          <div class="cr-b-stat"><strong>${data.recommendPercent}%</strong> would recommend to a friend</div>
          <div class="cr-b-stat">Size: <strong>${data.companySize}</strong></div>
          <div class="cr-b-stat">Salary (${title}): <strong>${salaryStr || 'n/a'}</strong></div>
        </div>
      </div>
      <details class="cr-b-accordion" ${data.interviews.length ? 'open' : ''}>
        <summary><i class="fa-solid fa-comments"></i> Interview reports (${title}) — ${data.interviews.length || 0}</summary>
        <div class="cr-b-accordion-body">
          ${
            data.interviews.length
              ? data.interviews.map((iv) => `<p style="margin-bottom:10px;"><strong>${iv.outcome}</strong> (${iv.difficulty})<br>${iv.processSummary}</p>`).join('')
              : '<span class="cr-na">No interview data on Glassdoor for this title.</span>'
          }
        </div>
      </details>
    </section>`;
}

function renderVariantC(state, data) {
  if (state === 'empty') {
    return `
      <section class="cr-section">
        ${sectionHeaderHtml()}
        ${emptyBlockHtml('A')}
      </section>`;
  }
  if (state === 'loading') {
    return `
      <section class="cr-section">
        ${sectionHeaderHtml()}
        ${loadingHtml()}
      </section>`;
  }

  const salaryStr = formatSalary(data.salary);
  const title = data.glassdoorJobTitle || 'QA Engineer';

  return `
    <section class="cr-section">
      ${sectionHeaderHtml({ data, showActions: true })}
      <div class="cr-c-dossier">
        <div class="cr-c-block">
          <div class="cr-c-block-label">Employee sentiment</div>
          <div class="cr-c-block-body">Overall rating <strong>${data.rating} / 5</strong> from ${data.reviewCount.toLocaleString()} reviews. <strong>${data.recommendPercent}%</strong> of employees would recommend the company to a friend. Company size: <strong>${data.companySize}</strong>.</div>
        </div>
        <div class="cr-c-block">
          <div class="cr-c-block-label">Compensation (${title})</div>
          <div class="cr-c-block-body">${salaryStr ? `Median base pay reported as <strong>${salaryStr}</strong>.` : '<span class="cr-na">No salary submissions on Glassdoor for this title.</span>'}</div>
        </div>
        <div class="cr-c-block">
          <div class="cr-c-block-label">Interview process (${title})</div>
          <div class="cr-c-block-body">
            ${
              data.interviews.length
                ? data.interviews
                    .map(
                      (iv) => `
              <blockquote class="cr-c-quote">
                ${iv.processSummary}
                <span class="cr-c-quote-meta">${iv.difficulty || '—'} difficulty · ${iv.outcome || '—'}</span>
              </blockquote>`,
                    )
                    .join('')
                : '<span class="cr-na">No interview reports for this title.</span>'
            }
          </div>
        </div>
        <div class="cr-c-footer-actions">
          <button type="button" data-demo="refresh">↻ Refresh research</button>
          <button type="button" class="warn" data-demo="wrong-company">Wrong company?</button>
          <button type="button" data-demo="spend-modal" style="margin-left:auto; color:var(--text-muted);">Preview spend modal</button>
        </div>
      </div>
    </section>`;
}

function renderCompanyResearch(variant, state) {
  const data =
    state === 'full' ? MOCK_RESEARCH.full : state === 'sparse' ? MOCK_RESEARCH.sparse : null;
  if (variant === 'B') return renderVariantB(state, data);
  if (variant === 'C') return renderVariantC(state, data);
  return renderVariantA(state, data);
}

function buildSpendModalBody(partialCache) {
  const slices = partialCache
    ? [
        { name: 'Company search + overview', status: 'cached' },
        { name: 'Salary · QA Engineer', status: 'billable' },
        { name: 'Interviews · QA Engineer', status: 'billable' },
      ]
    : [
        { name: 'Company search', status: 'billable' },
        { name: 'Company overview', status: 'billable' },
        { name: 'Salary · Senior QA Engineer (Hybrid)', status: 'billable' },
        { name: 'Interviews · Senior QA Engineer (Hybrid)', status: 'billable' },
      ];

  const billable = slices.filter((s) => s.status === 'billable').length;

  return `
    <div class="spend-modal-warn">
      <i class="fa-solid fa-triangle-exclamation" style="margin-top:2px"></i>
      <span>Company research uses Glassdoor via Apify and <b>spends real credits</b>.</span>
    </div>
    <div class="cr-spend-slices">
      ${slices
        .map(
          (s) => `
        <div class="cr-spend-slice-row">
          <span>${s.name}</span>
          <span class="${s.status}">${s.status === 'cached' ? 'cached ✓' : 'will fetch'}</span>
        </div>`,
        )
        .join('')}
    </div>
    <div class="cr-spend-title-field">
      <label for="cr-glassdoor-title">Glassdoor job title</label>
      <input id="cr-glassdoor-title" type="text" value="QA Engineer" />
      <div style="font-size:0.72rem; color:var(--text-muted); margin-top:4px;">Used for salary and interview lookup — shorten noisy listing titles.</div>
    </div>
    <div class="spend-estimate" style="margin-top:14px;">
      <div class="spend-estimate-label">Estimated spend</div>
      <div class="spend-estimate-big">${billable} Apify run${billable > 1 ? 's' : ''} · estimated ~$${(billable * 0.03).toFixed(2)}</div>
    </div>`;
}

function openPrototypeSpendModal(partialCache = false) {
  const modal = document.getElementById('spend-confirmation-modal');
  if (!modal) return;
  document.getElementById('spend-modal-title').textContent = 'Research company?';
  document.getElementById('spend-modal-subtitle').textContent = 'Glassdoor via Apify';
  document.getElementById('spend-modal-body').innerHTML = buildSpendModalBody(partialCache);
  document.getElementById('spend-modal-cancel').style.display = '';
  document.getElementById('spend-modal-confirm').innerHTML = '<i class="fa-solid fa-play"></i> Proceed';
  modal.style.display = 'flex';
}

function closeSpendModal() {
  const modal = document.getElementById('spend-confirmation-modal');
  if (modal) modal.style.display = 'none';
}

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    variant: (params.get('variant') || 'A').toUpperCase(),
    state: params.get('state') || 'sparse',
  };
}

function setParam(key, value) {
  const params = new URLSearchParams(window.location.search);
  params.set(key, value);
  window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
}

function cycleVariant(delta) {
  const { variant } = getParams();
  const idx = VARIANTS.findIndex((v) => v.key === variant);
  const next = VARIANTS[(idx + delta + VARIANTS.length) % VARIANTS.length];
  setParam('variant', next.key);
  render();
}

function renderStateChips() {
  const { state } = getParams();
  return STATES.map(
    (s) =>
      `<a class="prototype-chip${s === state ? ' is-active' : ''}" href="?variant=${getParams().variant}&state=${s}">${s}</a>`,
  ).join('');
}

function render() {
  const { variant, state } = getParams();
  const v = VARIANTS.find((x) => x.key === variant) || VARIANTS[0];
  const validState = STATES.includes(state) ? state : 'sparse';

  document.getElementById('prototype-variant-label').textContent = `${v.key} — ${v.name}`;
  document.getElementById('prototype-state-chips').innerHTML = renderStateChips();

  const job = { ...MOCK_JOB };
  if (validState === 'full') {
    job.company = 'TechVentures Inc.';
    job.title = 'QA Engineer';
  }

  document.getElementById('prototype-drawer-body').innerHTML = `
    <div class="drawer-header">
      <h2 class="drawer-header-title">${job.title}</h2>
      <div class="drawer-header-actions">
        <span class="match-pill match-mid" style="font-size:1.1rem; padding: 4px 10px;">${job.matchScore}% Match</span>
      </div>
    </div>
    <div style="display:flex; flex-direction:column; gap:14px;">
      ${buildJobInfoHtml(job)}
      ${renderCompanyResearch(v.key, validState)}
    </div>
    <div style="margin-top:20px; padding-top:14px; border-top:1px dashed var(--border-color); font-size:0.75rem; color:var(--text-muted);">
      Prototype controls: <button type="button" class="cr-btn-ghost" data-demo="spend-modal">Spend modal (full fetch)</button>
      <button type="button" class="cr-btn-ghost" data-demo="spend-partial">Spend modal (partial cache)</button>
    </div>`;

  document.querySelectorAll('[data-demo="research"]').forEach((btn) => {
    btn.addEventListener('click', () => openPrototypeSpendModal(false));
  });
  document.querySelectorAll('[data-demo="spend-modal"]').forEach((btn) => {
    btn.addEventListener('click', () => openPrototypeSpendModal(false));
  });
  document.querySelectorAll('[data-demo="spend-partial"]').forEach((btn) => {
    btn.addEventListener('click', () => openPrototypeSpendModal(true));
  });
  document.querySelectorAll('[data-demo="refresh"]').forEach((btn) => {
    btn.addEventListener('click', () => openPrototypeSpendModal(true));
  });
  document.querySelectorAll('[data-demo="wrong-company"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      alert('PROTOTYPE: Would open Glassdoor company picker (top 3 results) and clear cache.');
    });
  });
}

function bindSwitcher() {
  document.getElementById('prototype-prev')?.addEventListener('click', () => cycleVariant(-1));
  document.getElementById('prototype-next')?.addEventListener('click', () => cycleVariant(1));

  document.getElementById('spend-modal-cancel')?.addEventListener('click', closeSpendModal);
  document.getElementById('spend-modal-confirm')?.addEventListener('click', () => {
    closeSpendModal();
    setParam('state', 'loading');
    render();
    setTimeout(() => {
      setParam('state', 'sparse');
      render();
    }, 1800);
  });

  document.addEventListener('keydown', (e) => {
    const tag = e.target?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      cycleVariant(-1);
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      cycleVariant(1);
    }
    if (e.key === 'Escape') closeSpendModal();
  });
}

export function bootstrapCompanyResearchPrototype() {
  bindSwitcher();
  render();
}
