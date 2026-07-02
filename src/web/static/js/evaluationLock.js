/** Evaluation Lock UI — batch-evaluation assessing indicator and cancel control. */

export function createEvaluationLockController({ addLogLine, onLockStateChange }) {
  let evaluationLockActive = false;
  let evaluationLockPollTimer = null;

  function applyEvaluationLockUI(status) {
    evaluationLockActive = Boolean(status && status.active);
    const indicator = document.getElementById('evaluation-lock-indicator');
    const textEl = document.getElementById('evaluation-lock-text');
    const cancelBtn = document.getElementById('evaluation-lock-cancel');
    const jobCount = status && status.jobCount ? status.jobCount : 0;

    if (indicator) {
      indicator.hidden = !evaluationLockActive;
    }
    if (textEl) {
      textEl.textContent = `Assessing ${jobCount} job${jobCount === 1 ? '' : 's'}…`;
    }
    if (cancelBtn) {
      cancelBtn.disabled = false;
    }

    const btnPanel = document.getElementById('kb-scrape-btn-panel');
    if (btnPanel && evaluationLockActive) {
      btnPanel.disabled = true;
      btnPanel.innerHTML = '<i class="fa-solid fa-lock"></i> Assessment in progress';
    } else if (btnPanel && !btnPanel.innerHTML.includes('Running')) {
      onLockStateChange();
    }
  }

  async function refreshEvaluationLockStatus() {
    try {
      const response = await fetch('/api/evaluation-lock');
      if (!response.ok) return;
      const status = await response.json();
      applyEvaluationLockUI(status);
    } catch (_err) {
      // Backend may be offline during local dev; ignore.
    }
  }

  function initEvaluationLockPolling() {
    refreshEvaluationLockStatus();
    if (evaluationLockPollTimer) {
      clearInterval(evaluationLockPollTimer);
    }
    evaluationLockPollTimer = setInterval(refreshEvaluationLockStatus, 15000);
  }

  async function cancelEvaluation() {
    const cancelBtn = document.getElementById('evaluation-lock-cancel');
    if (cancelBtn) {
      cancelBtn.disabled = true;
    }
    addLogLine('Cancelling in-flight batch evaluation jobs…', 'warning');
    try {
      const response = await fetch('/api/evaluation-lock/cancel', { method: 'POST' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.message || `HTTP ${response.status}`);
      }
      addLogLine(`Cancelled ${body.cancelled || 0} batch job(s). Jobs remain in Scraped.`, 'success');
      applyEvaluationLockUI(body.active === false ? { active: false, jobCount: 0 } : body);
      await refreshEvaluationLockStatus();
    } catch (err) {
      addLogLine(`Failed to cancel evaluation: ${err.message}`, 'error');
      if (cancelBtn) cancelBtn.disabled = false;
    }
  }

  return {
    initEvaluationLockPolling,
    cancelEvaluation,
    isEvaluationLockActive: () => evaluationLockActive,
    applyEvaluationLockUI,
    refreshEvaluationLockStatus,
  };
}
