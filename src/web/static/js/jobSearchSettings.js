/** Job Search Settings — region pickers, scrape trigger, and settings panel. */

import { clampPerRegionLimit, PER_REGION_LIMIT_DEFAULT, PER_REGION_LIMIT_STEP } from './perRegionLimit.js';
import { showScrapeSpendConfirmModal } from './spendConfirmation.js';
import {
  ACTIVE_SCRAPE_LOG_SKIP_KEY,
  ACTIVE_SCRAPE_TASK_KEY,
} from './taskLogClient.js';

export function createJobSearchSettingsController({
  addLogLine,
  closeTaskLogStreamQuietly,
  connectTaskLogStream,
  expandLogsConsole,
  getActiveResume,
  integrateSearchResultFromStream,
  isEvaluationLockActive,
  refreshBoardQuietly = null,
  taskLog,
}) {
  const COUNTRY_CODE_MAP = { us: 'US', ca: 'CA', gb: 'GB', de: 'DE' };
  const COUNTRY_LABELS = { US: 'United States', CA: 'Canada', GB: 'United Kingdom', DE: 'Germany' };
  const COUNTRY_ORDER = ['US', 'CA', 'GB', 'DE'];
  let regionsMap = {};
  let activeRegionTab = 'US';
  const selectedSearchRegions = new Set();

  function regionSelectionKey(country, region) {
    return `${country}|${region}`;
  }

  function resetScrapeButtons() {
    updateScrapeRunButtonState();
  }

  function getSelectedCountries() {
    const codes = new Set(getSelectedSearchRegions().map(r => r.country));
    return [...codes].map(code => {
      const entry = Object.entries(COUNTRY_CODE_MAP).find(([, v]) => v === code);
      return entry ? entry[0] : code.toLowerCase();
    });
  }

  function getSelectedSearchRegions() {
    return [...selectedSearchRegions].map(key => {
      const [country, ...rest] = key.split('|');
      return { country, region: rest.join('|') };
    }).sort((a, b) => a.country.localeCompare(b.country) || a.region.localeCompare(b.region));
  }

  function countSelectedRegionsForCountry(code) {
    let count = 0;
    for (const key of selectedSearchRegions) {
      if (key.startsWith(`${code}|`)) count += 1;
    }
    return count;
  }

  function isSearchRegionsValid() {
    return selectedSearchRegions.size > 0;
  }

  function updateScrapeRunButtonState() {
    const btnPanel = document.getElementById('kb-scrape-btn-panel');
    const hint = document.getElementById('kb-region-hint');
    if (!btnPanel) return;

    const running = btnPanel.innerHTML.includes('Running');
    if (running) return;

    const regionsValid = isSearchRegionsValid();

    if (hint) {
      hint.hidden = regionsValid || isEvaluationLockActive();
    }

    if (isEvaluationLockActive()) {
      btnPanel.disabled = true;
      btnPanel.innerHTML = '<i class="fa-solid fa-lock"></i> Assessment in progress';
      return;
    }

    btnPanel.disabled = !regionsValid;
    btnPanel.innerHTML = '<i class="fa-solid fa-play"></i> Run Scraper with Filters';
  }

  function toggleSearchRegion(country, region) {
    const key = regionSelectionKey(country, region);
    if (selectedSearchRegions.has(key)) selectedSearchRegions.delete(key);
    else selectedSearchRegions.add(key);
    renderRegionPickers();
  }

  function renderRegionPickers() {
    const tabsEl = document.getElementById('kb-region-country-tabs');
    const chipsEl = document.getElementById('kb-region-chips');
    if (!tabsEl || !chipsEl || !regionsMap) return;

    tabsEl.innerHTML = '';
    for (const code of COUNTRY_ORDER) {
      if (!regionsMap[code]) continue;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'region-country-tab' + (code === activeRegionTab ? ' active' : '');
      const count = countSelectedRegionsForCountry(code);
      btn.innerHTML = (COUNTRY_LABELS[code] || code)
        + (count ? `<span class="region-tab-badge">${count}</span>` : '');
      btn.addEventListener('click', () => {
        activeRegionTab = code;
        renderRegionPickers();
      });
      tabsEl.appendChild(btn);
    }

    chipsEl.innerHTML = '';
    const regions = regionsMap[activeRegionTab] || [];
    for (const region of regions) {
      const key = regionSelectionKey(activeRegionTab, region);
      const selected = selectedSearchRegions.has(key);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'region-chip' + (selected ? ' selected' : '');
      chip.textContent = region;
      chip.addEventListener('click', () => toggleSearchRegion(activeRegionTab, region));
      chipsEl.appendChild(chip);
    }

    updateScrapeRunButtonState();
  }

  async function initSearchRegionPickers() {
    try {
      const resp = await fetch('/api/regions');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      regionsMap = await resp.json();
      activeRegionTab = COUNTRY_ORDER.find(code => regionsMap[code]) || 'US';
      renderRegionPickers();
    } catch (err) {
      console.error('Failed to load regions:', err);
    }
  }

  function initPerRegionLimitStepper() {
    const input = document.getElementById('kb-per-region-limit');
    const dec = document.getElementById('kb-per-region-dec');
    const inc = document.getElementById('kb-per-region-inc');
    if (!input) return;

    const applyClamp = () => {
      input.value = clampPerRegionLimit(input.value);
    };

    input.addEventListener('change', applyClamp);
    input.addEventListener('blur', applyClamp);

    if (dec) {
      dec.addEventListener('click', () => {
        input.value = clampPerRegionLimit(parseInt(input.value, 10) - PER_REGION_LIMIT_STEP);
      });
    }
    if (inc) {
      inc.addEventListener('click', () => {
        input.value = clampPerRegionLimit(parseInt(input.value, 10) + PER_REGION_LIMIT_STEP);
      });
    }
  }

  async function triggerScrapeRun() {
    if (isEvaluationLockActive()) {
      addLogLine('Cannot start scrape: batch evaluation is in progress. Cancel or wait for completion.', 'warning');
      return;
    }
    if (!isSearchRegionsValid()) {
      addLogLine('Cannot start scrape: pick at least one Search Region.', 'warning');
      return;
    }
    let query = "QA Engineer";
    let remote_type = "any";
    let seniority = "any";
    let salary = "";
    let company_size = "any";
    let employment_type = "any";
    
    const queryEl = document.getElementById('kb-filter-position');
    if (queryEl) query = queryEl.value;

    const remoteEls = document.querySelectorAll('input[name="kb-filter-remote"]:checked');
    if (remoteEls.length > 0) {
      remote_type = Array.from(remoteEls).map(el => el.value).join(',');
    }

    const seniorityEls = document.querySelectorAll('input[name="kb-filter-seniority"]:checked');
    if (seniorityEls.length > 0) {
      seniority = Array.from(seniorityEls).map(el => el.value).join(',');
    }

    const salaryEl = document.getElementById('kb-filter-salary');
    if (salaryEl) salary = salaryEl.value;

    const sizeEls = document.querySelectorAll('input[name="kb-filter-size"]:checked');
    if (sizeEls.length > 0) {
      company_size = Array.from(sizeEls).map(el => el.value).join(',');
    }

    const employmentEls = document.querySelectorAll('input[name="kb-filter-employment"]:checked');
    if (employmentEls.length > 0) {
      employment_type = Array.from(employmentEls).map(el => el.value).join(',');
    }

    const platformEl = document.getElementById('kb-filter-platform');
    const platform = platformEl ? platformEl.value : "brightdata_linkedin";

    const countries = getSelectedCountries().join(',') || 'us';

    const timeEl = document.querySelector('input[name="kb-filter-time"]:checked');
    const time_range = timeEl ? timeEl.value : 'any';

    const search_regions = getSelectedSearchRegions();
    const limitEl = document.getElementById('kb-per-region-limit');
    let per_region_limit = clampPerRegionLimit(limitEl ? limitEl.value : PER_REGION_LIMIT_DEFAULT);

    const spendResult = await showScrapeSpendConfirmModal({
      query,
      searchRegions: search_regions,
      timeRange: time_range,
      perRegionLimit: per_region_limit,
      platform,
    });
    if (!spendResult.confirmed) return;

    per_region_limit = spendResult.perRegionLimit;
    if (limitEl) limitEl.value = per_region_limit;

    const mockEval = false;

    // Reveal logs console panel in UI
    const kbLogsPanel = document.getElementById('kb-logs-panel');
    if (kbLogsPanel) {
      kbLogsPanel.style.display = 'block';
    }
    expandLogsConsole();

    let logMsg = `Initiating async scraper task. Query: "${query}", Regions: [${search_regions.map(r => r.region + ' (' + r.country + ')').join(', ')}], Per-Region Limit: ${per_region_limit}, Countries: [${countries.toUpperCase()}], Time: ${time_range}, Engine: ${platform}`;
    let activeFilters = [];
    if (remote_type !== 'any') activeFilters.push(`Remote: ${remote_type}`);
    if (seniority !== 'any') activeFilters.push(`Seniority: ${seniority}`);
    if (salary) activeFilters.push(`Salary Min: ${salary}`);
    if (company_size !== 'any') activeFilters.push(`Company Size: ${company_size}`);
    if (employment_type !== 'any') activeFilters.push(`Employment Type: ${employment_type}`);
    if (activeFilters.length > 0) {
      logMsg += ` | Filters: [${activeFilters.join(', ')}]`;
    }
    addLogLine(logMsg, 'warning');
    
    // Disable buttons during action
    const btnPanel = document.getElementById('kb-scrape-btn-panel');
    if (btnPanel) {
      btnPanel.disabled = true;
      btnPanel.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running...';
    }

    // Connect to FastAPI SSE endpoint to stream logs
    closeTaskLogStreamQuietly(taskLog.getLogEventSource());
    taskLog.setLogEventSource(null);

    const url = `/api/search`;
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: query,
        search_regions: search_regions,
        per_region_limit: per_region_limit,
        platform: platform,
        active_resume: getActiveResume(),
        mock_eval: mockEval,
        remote_type: remote_type,
        seniority: seniority,
        salary: salary,
        company_size: company_size,
        employment_type: employment_type,
        countries: countries,
        time_range: time_range
      })
    })
    .then(response => {
      if (!response.ok) {
        // The backend IS reachable here — it answered with an error status
        // (e.g. 429 rate limit, 422 validation). Surface the real reason
        // instead of the catch-all "backend unavailable" message.
        return response.json().catch(() => ({})).then(body => {
          let detail = body && body.message;
          if (!detail && body && Array.isArray(body.detail)) {
            detail = body.detail.map(d => d.msg).join('; ');
          }
          const err = new Error(detail || `Server returned HTTP ${response.status}`);
          err.handled = true;
          err.status = response.status;
          throw err;
        });
      }
      return response.json();
    })
    .then(data => {
      const taskId = data.task_id;
      localStorage.setItem(ACTIVE_SCRAPE_TASK_KEY, taskId);
      localStorage.setItem(ACTIVE_SCRAPE_LOG_SKIP_KEY, '0');
      addLogLine(`FastAPI background task created: ${taskId}`, 'info');

      const maxReconnectAttempts = 5;
      const reconnectDelayMs = 2000;

      function attachScrapeLogStream(attempt) {
        taskLog.setLogEventSource(connectTaskLogStream(taskId, {
          skipKey: ACTIVE_SCRAPE_LOG_SKIP_KEY,
          taskKey: ACTIVE_SCRAPE_TASK_KEY,
          existingSource: taskLog.getLogEventSource(),
          clearStorageOnError: false,
          onResult(logData) {
            integrateSearchResultFromStream(logData);
          },
          onDone() {
            addLogLine('Scraper process complete.', 'success');
            resetScrapeButtons();
            if (typeof refreshBoardQuietly === 'function') {
              refreshBoardQuietly();
            }
          },
          onError() {
            if (attempt >= maxReconnectAttempts) {
              localStorage.removeItem(ACTIVE_SCRAPE_TASK_KEY);
              localStorage.removeItem(ACTIVE_SCRAPE_LOG_SKIP_KEY);
              addLogLine('Scraper SSE stream closed unexpectedly.', 'warning');
              resetScrapeButtons();
              if (typeof refreshBoardQuietly === 'function') {
                refreshBoardQuietly();
              }
              return;
            }
            addLogLine(
              `Scraper SSE stream interrupted — reconnecting (${attempt + 1}/${maxReconnectAttempts})…`,
              'warning'
            );
            window.setTimeout(() => {
              attachScrapeLogStream(attempt + 1);
            }, reconnectDelayMs);
          },
        }));
      }

      attachScrapeLogStream(0);
    })
    .catch(err => {
      if (err && err.handled) {
        // Backend responded with an error status — show its actual reason.
        console.warn(`Scraper request rejected (HTTP ${err.status}).`, err);
        addLogLine(`Could not start scraper — ${err.message}`, 'warning');
      } else {
        // Genuine connection failure (server down / restarting / network).
        console.warn("FastAPI backend not responding.", err);
        addLogLine("Could not start scraper — backend unavailable. Is the dashboard server running?", 'warning');
      }
      resetScrapeButtons();
    });
  }

  function toggleLogsHeight() {
    const consoleEl = document.getElementById('kb-logs-console');
    const btn = document.getElementById('toggle-logs-btn');
    if (consoleEl && btn) {
      const isShrunk = consoleEl.classList.toggle('shrunk');
      if (isShrunk) {
        btn.innerHTML = '<i class="fa-solid fa-chevron-down"></i> Expand';
        localStorage.setItem('panel-task-logs-collapsed', 'true');
      } else {
        btn.innerHTML = '<i class="fa-solid fa-chevron-up"></i> Collapse';
        localStorage.setItem('panel-task-logs-collapsed', 'false');
      }
    }
  }

  function initLogsConsoleState() {
    const stored = localStorage.getItem('panel-task-logs-collapsed');
    const isShrunk = stored !== 'false';
    const consoleEl = document.getElementById('kb-logs-console');
    const btn = document.getElementById('toggle-logs-btn');
    if (!consoleEl || !btn) return;
    if (isShrunk) {
      consoleEl.classList.add('shrunk');
      btn.innerHTML = '<i class="fa-solid fa-chevron-down"></i> Expand';
    } else {
      consoleEl.classList.remove('shrunk');
      btn.innerHTML = '<i class="fa-solid fa-chevron-up"></i> Collapse';
    }
  }

  function toggleJobSearchSettings() {
    const panel = document.getElementById('job-search-settings-body');
    const btn = document.getElementById('job-search-settings-toggle');
    const chevron = document.getElementById('settings-chevron');
    panel.classList.toggle('expanded');
    const isExpanded = panel.classList.contains('expanded');
    if (btn) {
      btn.innerHTML = isExpanded
        ? '<i class="fa-solid fa-chevron-up" id="settings-chevron" style="transition: transform var(--transition-fast);"></i> Hide'
        : '<i class="fa-solid fa-chevron-down" id="settings-chevron" style="transition: transform var(--transition-fast);"></i> Show';
    }
    if (chevron) chevron.style.transform = isExpanded ? 'rotate(180deg)' : 'rotate(0deg)';
    localStorage.setItem('panel-scraper-settings-collapsed', isExpanded ? 'false' : 'true');
  }

  function initJobSearchSettingsState() {
    const stored = localStorage.getItem('panel-scraper-settings-collapsed');
    const isCollapsed = stored !== 'false';
    const panel = document.getElementById('job-search-settings-body');
    const btn = document.getElementById('job-search-settings-toggle');
    if (!panel || !btn) return;
    if (isCollapsed) {
      panel.classList.remove('expanded');
      btn.innerHTML = '<i class="fa-solid fa-chevron-down" id="settings-chevron" style="transition: transform var(--transition-fast);"></i> Show';
    } else {
      panel.classList.add('expanded');
      btn.innerHTML = '<i class="fa-solid fa-chevron-up" id="settings-chevron" style="transition: transform var(--transition-fast);"></i> Hide';
    }
  }

  function resetKbFilters() {
    document.getElementById('kb-filter-position').value = 'Senior QA Automation';
    document.querySelectorAll('input[name="kb-filter-remote"]').forEach(cb => cb.checked = cb.value === 'remote');
    document.querySelectorAll('input[name="kb-filter-seniority"]').forEach(cb => cb.checked = cb.value === 'senior');
    document.querySelectorAll('input[name="kb-filter-size"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('input[name="kb-filter-employment"]').forEach(cb => cb.checked = false);
    selectedSearchRegions.clear();
    activeRegionTab = COUNTRY_ORDER.find(code => regionsMap[code]) || 'US';
    
    const salaryEl = document.getElementById('kb-filter-salary');
    if (salaryEl) salaryEl.value = '';
    
    const platformEl = document.getElementById('kb-filter-platform');
    if (platformEl) platformEl.value = 'brightdata_linkedin';

    const limitEl = document.getElementById('kb-per-region-limit');
    if (limitEl) limitEl.value = PER_REGION_LIMIT_DEFAULT;
    
    document.querySelectorAll('input[name="kb-filter-time"]').forEach(rb => rb.checked = rb.value === 'any');

    renderRegionPickers();
    addLogLine("Kanban scraper settings reset to default values.", 'info');
  }

  return {
    triggerScrapeRun,
    resetKbFilters,
    toggleJobSearchSettings,
    initJobSearchSettingsState,
    initSearchRegionPickers,
    initPerRegionLimitStepper,
    initLogsConsoleState,
    toggleLogsHeight,
    resetScrapeButtons,
    updateScrapeRunButtonState,
    getSelectedSearchRegions,
  };
}
