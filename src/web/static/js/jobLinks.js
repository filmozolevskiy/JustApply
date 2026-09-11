/** Pure Job Link path helpers — `/jobs/{id}` means that job's drawer is open. */

export const BOARD_ROOT_PATH = '/';

export function buildJobLinkPath(jobId) {
  return `/jobs/${jobId}`;
}

/**
 * Parse a location pathname into a Job Link result.
 * @returns {{ type: 'job', id: number } | { type: 'board' } | { type: 'invalid' }}
 */
export function parseJobLinkPath(pathname) {
  const raw = typeof pathname === 'string' ? pathname : '';
  const path = raw.split('?')[0].split('#')[0];

  if (
    path === '/' ||
    path === '/dashboard' ||
    path === '/jobs' ||
    path === '/jobs/'
  ) {
    return { type: 'board' };
  }

  const match = path.match(/^\/jobs\/([^/]+)\/?$/);
  if (!match) {
    return { type: 'board' };
  }

  const segment = match[1];
  if (!/^\d+$/.test(segment)) {
    return { type: 'invalid' };
  }

  return { type: 'job', id: Number(segment) };
}

export function pushJobLinkHistory(jobId) {
  if (typeof history === 'undefined' || typeof location === 'undefined') return;
  const path = buildJobLinkPath(jobId);
  if (location.pathname === path) return;
  history.pushState({ jobLink: jobId }, '', path);
}

export function pushBoardRootHistory() {
  if (typeof history === 'undefined' || typeof location === 'undefined') return;
  if (location.pathname === BOARD_ROOT_PATH) return;
  history.pushState({ jobLink: null }, '', BOARD_ROOT_PATH);
}

/** Restore `/jobs/{id}` after Cancel on URL leave (replace, do not push). */
export function restoreJobLinkHistory(jobId) {
  if (typeof history === 'undefined' || typeof location === 'undefined') return;
  const path = buildJobLinkPath(jobId);
  if (location.pathname === path) return;
  history.replaceState({ jobLink: jobId }, '', path);
}
