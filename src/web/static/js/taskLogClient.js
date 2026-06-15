/** Task log console and SSE streaming for background jobs. */

export const SESSION_LOGS_KEY = 'taskLogsSession';
export const SESSION_LOGS_MAX = 200;
export const ACTIVE_SCRAPE_TASK_KEY = 'activeScrapeTaskId';
export const ACTIVE_SCRAPE_LOG_SKIP_KEY = 'activeScrapeTaskLogSkip';
export const ACTIVE_ENRICH_TASK_KEY = 'activeEnrichTaskId';
export const ACTIVE_ENRICH_LOG_SKIP_KEY = 'activeEnrichTaskLogSkip';

export function handleTaskLogMessage(logData, { addLogLine, onResult, onDone }) {
  if (logData.type === 'log') {
    addLogLine(logData.message, logData.level);
    return 'log';
  }
  if (logData.type === 'result') {
    if (onResult) onResult(logData);
    return 'result';
  }
  if (logData.type === 'done') {
    if (onDone) onDone(logData);
    return 'done';
  }
  return null;
}

export function createTaskLogClient() {
  let logEventSource = null;
  let enrichEventSource = null;
  let pageUnloading = false;
  let sessionLogs = [];

  function persistSessionLogs() {
    try {
      localStorage.setItem(SESSION_LOGS_KEY, JSON.stringify(sessionLogs));
    } catch (e) {
      console.warn('Failed to persist task logs', e);
    }
  }

  function renderLogLine(msg, level = 'info', ts = null) {
    const consoles = [
      document.getElementById('cc-logs-console'),
      document.getElementById('kb-logs-console'),
    ];
    const timeStr = ts
      ? new Date(ts).toTimeString().split(' ')[0]
      : new Date().toTimeString().split(' ')[0];

    consoles.forEach((consoleEl) => {
      if (!consoleEl) return;
      if (
        consoleEl.children.length === 1 &&
        consoleEl.children[0].innerText.includes('System initialized')
      ) {
        consoleEl.innerHTML = '';
      }
      const line = document.createElement('div');
      line.className = 'terminal-line';
      line.innerHTML = `
          <span class="terminal-time">${timeStr}</span>
          <span class="terminal-text ${level}">${msg}</span>
        `;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    });
  }

  function addLogLine(msg, level = 'info') {
    const ts = new Date().toISOString();
    renderLogLine(msg, level, ts);
    sessionLogs.push({ ts, message: msg, level });
    if (sessionLogs.length > SESSION_LOGS_MAX) {
      sessionLogs = sessionLogs.slice(-SESSION_LOGS_MAX);
    }
    persistSessionLogs();
  }

  function restoreSessionLogs() {
    try {
      const raw = localStorage.getItem(SESSION_LOGS_KEY);
      if (!raw) return;
      sessionLogs = JSON.parse(raw);
      if (!Array.isArray(sessionLogs)) {
        sessionLogs = [];
        return;
      }
      const consoles = [
        document.getElementById('cc-logs-console'),
        document.getElementById('kb-logs-console'),
      ];
      consoles.forEach((consoleEl) => {
        if (!consoleEl) return;
        consoleEl.innerHTML = '';
      });
      sessionLogs.forEach((entry) => {
        renderLogLine(entry.message, entry.level, entry.ts);
      });
      if (sessionLogs.length > 0) {
        const kbLogsPanel = document.getElementById('kb-logs-panel');
        if (kbLogsPanel) kbLogsPanel.style.display = 'block';
      }
    } catch (e) {
      console.warn('Failed to restore task logs', e);
      sessionLogs = [];
    }
  }

  function clearLogs() {
    sessionLogs = [];
    persistSessionLogs();
    const consoles = [
      document.getElementById('cc-logs-console'),
      document.getElementById('kb-logs-console'),
    ];
    consoles.forEach((consoleEl) => {
      if (consoleEl) {
        consoleEl.innerHTML =
          '<div class="terminal-line"><span class="terminal-time">' +
          new Date().toTimeString().split(' ')[0] +
          '</span><span class="terminal-text">Console cleared. Ready.</span></div>';
      }
    });
  }

  function bumpTaskLogSkip(storageKey) {
    const skip = parseInt(localStorage.getItem(storageKey) || '0', 10) + 1;
    localStorage.setItem(storageKey, String(skip));
    return skip;
  }

  function markPageUnloading() {
    pageUnloading = true;
  }

  function closeTaskLogStreamQuietly(source) {
    if (!source) return;
    source._intentionalClose = true;
    source.close();
  }

  function connectTaskLogStream(taskId, options = {}) {
    const {
      skipKey,
      taskKey,
      onResult,
      onDone,
      onError,
      existingSource = null,
    } = options;

    if (existingSource) {
      closeTaskLogStreamQuietly(existingSource);
    }

    const skip = parseInt(localStorage.getItem(skipKey) || '0', 10);
    const es = new EventSource(`/api/logs/${taskId}?skip=${skip}`);

    es.onmessage = function (event) {
      const logData = JSON.parse(event.data);
      if (logData.type === 'log') {
        addLogLine(logData.message, logData.level);
        bumpTaskLogSkip(skipKey);
      } else if (logData.type === 'result') {
        if (onResult) onResult(logData);
      } else if (logData.type === 'done') {
        closeTaskLogStreamQuietly(es);
        localStorage.removeItem(taskKey);
        localStorage.removeItem(skipKey);
        if (onDone) onDone(logData);
      }
    };

    es.onerror = function (err) {
      const intentional = es._intentionalClose || pageUnloading;
      closeTaskLogStreamQuietly(es);
      if (intentional) {
        return;
      }
      localStorage.removeItem(taskKey);
      localStorage.removeItem(skipKey);
      if (onError) onError(err);
    };

    return es;
  }

  function expandLogsConsole() {
    const consoleEl = document.getElementById('kb-logs-console');
    const btn = document.getElementById('toggle-logs-btn');
    if (consoleEl && consoleEl.classList.contains('shrunk') && btn) {
      consoleEl.classList.remove('shrunk');
      btn.innerHTML = '<i class="fa-solid fa-chevron-up"></i> Collapse';
      localStorage.setItem('panel-task-logs-collapsed', 'false');
    }
  }

  return {
    addLogLine,
    bumpTaskLogSkip,
    clearLogs,
    closeTaskLogStreamQuietly,
    connectTaskLogStream,
    expandLogsConsole,
    getEnrichEventSource: () => enrichEventSource,
    getLogEventSource: () => logEventSource,
    markPageUnloading,
    restoreSessionLogs,
    setEnrichEventSource: (source) => {
      enrichEventSource = source;
    },
    setLogEventSource: (source) => {
      logEventSource = source;
    },
  };
}
