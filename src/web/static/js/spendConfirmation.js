/** Spend Confirmation modal — Apify actions and scrape checkout receipt. */

import { clampPerRegionLimit, PER_REGION_LIMIT_STEP } from './perRegionLimit.js';

let spendModalResolver = null;
let spendModalKeyHandler = null;

function escapeSpendHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function cleanupSpendModal() {
  const modal = document.getElementById('spend-confirmation-modal');
  if (modal) modal.style.display = 'none';
  if (spendModalKeyHandler) {
    document.removeEventListener('keydown', spendModalKeyHandler);
    spendModalKeyHandler = null;
  }
  spendModalResolver = null;
}

function finishSpendModal(confirmed) {
  const resolve = spendModalResolver;
  cleanupSpendModal();
  if (resolve) resolve(confirmed);
}

function dismissSpendModalFromOverlay(e) {
  const modal = document.getElementById('spend-confirmation-modal');
  if (!modal || !spendModalResolver) return;
  if (e && e.target === modal) finishSpendModal(false);
}

function buildApifySpendBodyHtml(actionLabel, streamLines, runs, costStr) {
  const linesHtml = streamLines
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const text = line.replace(/^- /, '');
      return `<div class="spend-stream-line">${escapeSpendHtml(text)}</div>`;
    })
    .join('');
  const runLabel = `${runs} Apify run${runs > 1 ? 's' : ''}`;
  return `
    <div class="spend-modal-warn">
      <i class="fa-solid fa-triangle-exclamation" style="margin-top:2px"></i>
      <span>${escapeSpendHtml(actionLabel)} will fetch from LinkedIn via Apify and <b>spends real credits</b>.</span>
    </div>
    <div class="spend-stream-list">${linesHtml}</div>
    <div class="spend-estimate">
      <div class="spend-estimate-label">Estimated spend</div>
      <div class="spend-estimate-big">${escapeSpendHtml(runLabel)} · estimated ${escapeSpendHtml(costStr)}</div>
    </div>
  `;
}

function openSpendModal({ title, subtitle, bodyHtml, confirmLabel, showCancel }) {
  return new Promise((resolve) => {
    const modal = document.getElementById('spend-confirmation-modal');
    const titleEl = document.getElementById('spend-modal-title');
    const subtitleEl = document.getElementById('spend-modal-subtitle');
    const bodyEl = document.getElementById('spend-modal-body');
    const cancelBtn = document.getElementById('spend-modal-cancel');
    const confirmBtn = document.getElementById('spend-modal-confirm');
    if (!modal || !titleEl || !subtitleEl || !bodyEl || !cancelBtn || !confirmBtn) {
      resolve(false);
      return;
    }

    spendModalResolver = resolve;
    titleEl.textContent = title;
    subtitleEl.textContent = subtitle || 'LinkedIn via Apify';
    bodyEl.innerHTML = bodyHtml;
    confirmBtn.innerHTML = `<i class="fa-solid fa-play"></i> ${escapeSpendHtml(confirmLabel || 'Proceed')}`;
    cancelBtn.style.display = showCancel ? '' : 'none';

    const onCancel = () => finishSpendModal(false);
    const onConfirm = () => finishSpendModal(true);

    cancelBtn.onclick = onCancel;
    confirmBtn.onclick = onConfirm;

    spendModalKeyHandler = (e) => {
      if (e.key === 'Escape') finishSpendModal(false);
    };
    document.addEventListener('keydown', spendModalKeyHandler);

    modal.style.display = 'flex';
    (showCancel ? cancelBtn : confirmBtn).focus();
  });
}

function showSpendConfirmModal({ title, subtitle, bodyHtml, confirmLabel }) {
  return openSpendModal({
    title,
    subtitle,
    bodyHtml,
    confirmLabel: confirmLabel || 'Proceed',
    showCancel: true,
  });
}

function showSpendAckModal({ title, message, okLabel }) {
  return openSpendModal({
    title,
    subtitle: '',
    bodyHtml: `<div class="spend-modal-message">${escapeSpendHtml(message)}</div>`,
    confirmLabel: okLabel || 'OK',
    showCancel: false,
  }).then(() => {});
}

function confirmDiscardUnsavedEdits(message) {
  return showSpendConfirmModal({
    title: 'Unsaved changes',
    subtitle: 'Your edits have not been posted.',
    bodyHtml: `<div class="spend-modal-message">${escapeSpendHtml(message)}</div>`,
    confirmLabel: 'Discard',
  });
}

const SCRAPE_COST_PER_RECORD = 0.0015;

const COUNTRY_DISPLAY_NAMES = {
  US: 'United States',
  CA: 'Canada',
  GB: 'United Kingdom',
  DE: 'Germany',
};

const TIME_RANGE_LABELS = {
  any: 'Anytime',
  past_24_hours: 'Past 24 hours',
  past_week: 'Past week',
  past_month: 'Past month',
};

function groupSearchRegionsByCountry(searchRegions) {
  const grouped = new Map();
  for (const { country, region } of searchRegions) {
    if (!grouped.has(country)) grouped.set(country, []);
    grouped.get(country).push(region);
  }
  const countryOrder = ['US', 'CA', 'GB', 'DE'];
  const ordered = [];
  for (const code of countryOrder) {
    if (grouped.has(code)) ordered.push([code, grouped.get(code)]);
  }
  for (const [code, regions] of grouped) {
    if (!countryOrder.includes(code)) ordered.push([code, regions]);
  }
  return ordered;
}

function formatTimeRangeLabel(timeRange) {
  return TIME_RANGE_LABELS[timeRange] || timeRange;
}

function recomputeScrapeSpendEstimate(regionCount, perRegionLimit) {
  const limit = clampPerRegionLimit(perRegionLimit);
  const maxPostings = regionCount * limit;
  const maxSpend = maxPostings * SCRAPE_COST_PER_RECORD;
  return { limit, maxPostings, maxSpend };
}

function buildScrapeSpendReceiptBodyHtml({ query, groupedRegions, timeRangeLabel, regionCount, perRegionLimit }) {
  const { maxPostings, maxSpend } = recomputeScrapeSpendEstimate(regionCount, perRegionLimit);
  const limit = clampPerRegionLimit(perRegionLimit);

  let regionsHtml = '';
  for (const [country, regions] of groupedRegions) {
    const displayName = COUNTRY_DISPLAY_NAMES[country] || country;
    const chips = regions
      .map((r) => `<span class="spend-region-chip">${escapeSpendHtml(r)}</span>`)
      .join('');
    regionsHtml += `
      <div class="spend-country-head">${escapeSpendHtml(displayName)}</div>
      <div class="spend-region-chips">${chips}</div>
    `;
  }

  return `
    <div class="spend-receipt-grid">
      <div class="spend-receipt-left">
        <h3 class="spend-receipt-title">Run live LinkedIn scrape?</h3>
        <div class="spend-receipt-sub">Searching <span class="spend-kw">${escapeSpendHtml(query)}</span> in title / description · posted in the <b>${escapeSpendHtml(timeRangeLabel)}</b>.</div>
        ${regionsHtml}
      </div>
      <div class="spend-receipt-right">
        <div class="spend-receipt-warn">
          <i class="fa-solid fa-triangle-exclamation"></i> Spends real Bright Data credits
        </div>
        <div class="spend-receipt-line"><span>Search regions</span><span class="spend-receipt-val" id="scrape-spend-region-count">${regionCount}</span></div>
        <div class="spend-receipt-line">
          <span>Per-region limit</span>
          <span class="spend-receipt-stepper">
            <button type="button" id="scrape-spend-limit-dec" aria-label="Decrease">&minus;</button>
            <input id="scrape-spend-limit" type="number" min="25" max="1000" step="25" value="${limit}" aria-label="Jobs per region">
            <button type="button" id="scrape-spend-limit-inc" aria-label="Increase">+</button>
          </span>
        </div>
        <div class="spend-receipt-line"><span>Max postings</span><span class="spend-receipt-val" id="scrape-spend-max-postings">${maxPostings.toLocaleString()}</span></div>
        <div class="spend-receipt-line"><span>Cost per record</span><span class="spend-receipt-val">× $0.0015</span></div>
        <div class="spend-receipt-divider"></div>
        <div class="spend-receipt-total"><span class="spend-receipt-sub">Max spend</span><span class="spend-receipt-amt" id="scrape-spend-max-spend">~$${maxSpend.toFixed(2)}</span></div>
        <div class="spend-receipt-note">Actual cost depends on how many postings match — this is the ceiling.</div>
      </div>
    </div>
  `;
}

function showScrapeSpendConfirmModal({ query, searchRegions, timeRange, perRegionLimit }) {
  const regionCount = searchRegions.length;
  const groupedRegions = groupSearchRegionsByCountry(searchRegions);
  const timeRangeLabel = formatTimeRangeLabel(timeRange);
  const bodyHtml = buildScrapeSpendReceiptBodyHtml({
    query,
    groupedRegions,
    timeRangeLabel,
    regionCount,
    perRegionLimit,
  });

  return new Promise((resolve) => {
    const modal = document.getElementById('spend-confirmation-modal');
    const modalContent = modal?.querySelector('.spend-modal-content');
    const headEl = modal?.querySelector('.spend-modal-head');
    const bodyEl = document.getElementById('spend-modal-body');
    const cancelBtn = document.getElementById('spend-modal-cancel');
    const confirmBtn = document.getElementById('spend-modal-confirm');
    if (!modal || !bodyEl || !cancelBtn || !confirmBtn) {
      resolve({ confirmed: false, perRegionLimit });
      return;
    }

    if (modalContent) modalContent.classList.add('spend-modal-receipt');
    if (headEl) headEl.style.display = 'none';

    bodyEl.innerHTML = bodyHtml;
    confirmBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run scraper';
    cancelBtn.style.display = '';

    const limitInput = document.getElementById('scrape-spend-limit');
    const maxPostingsEl = document.getElementById('scrape-spend-max-postings');
    const maxSpendEl = document.getElementById('scrape-spend-max-spend');
    const decBtn = document.getElementById('scrape-spend-limit-dec');
    const incBtn = document.getElementById('scrape-spend-limit-inc');

    const updateEstimate = () => {
      if (!limitInput || !maxPostingsEl || !maxSpendEl) return;
      const { limit, maxPostings, maxSpend } = recomputeScrapeSpendEstimate(regionCount, limitInput.value);
      limitInput.value = limit;
      maxPostingsEl.textContent = maxPostings.toLocaleString();
      maxSpendEl.textContent = '~$' + maxSpend.toFixed(2);
    };

    const onDec = () => {
      if (!limitInput) return;
      limitInput.value = clampPerRegionLimit(parseInt(limitInput.value, 10) - PER_REGION_LIMIT_STEP);
      updateEstimate();
    };

    const onInc = () => {
      if (!limitInput) return;
      limitInput.value = clampPerRegionLimit(parseInt(limitInput.value, 10) + PER_REGION_LIMIT_STEP);
      updateEstimate();
    };

    if (limitInput) {
      limitInput.addEventListener('input', updateEstimate);
      limitInput.addEventListener('change', updateEstimate);
    }
    if (decBtn) decBtn.addEventListener('click', onDec);
    if (incBtn) incBtn.addEventListener('click', onInc);

    const cleanupReceiptMode = () => {
      if (modalContent) modalContent.classList.remove('spend-modal-receipt');
      if (headEl) headEl.style.display = '';
      if (limitInput) {
        limitInput.removeEventListener('input', updateEstimate);
        limitInput.removeEventListener('change', updateEstimate);
      }
      if (decBtn) decBtn.removeEventListener('click', onDec);
      if (incBtn) incBtn.removeEventListener('click', onInc);
    };

    const finishScrapeModal = (confirmed) => {
      const finalLimit = clampPerRegionLimit(limitInput ? limitInput.value : perRegionLimit);
      cleanupReceiptMode();
      cleanupSpendModal();
      resolve({ confirmed, perRegionLimit: finalLimit });
    };

    spendModalResolver = finishScrapeModal;

    cancelBtn.onclick = () => finishScrapeModal(false);
    confirmBtn.onclick = () => finishScrapeModal(true);

    spendModalKeyHandler = (e) => {
      if (e.key === 'Escape') finishScrapeModal(false);
    };
    document.addEventListener('keydown', spendModalKeyHandler);

    modal.style.display = 'flex';
    cancelBtn.focus();
  });
}

export {
  dismissSpendModalFromOverlay,
  showSpendConfirmModal,
  showSpendAckModal,
  confirmDiscardUnsavedEdits,
  showScrapeSpendConfirmModal,
  buildApifySpendBodyHtml,
};
