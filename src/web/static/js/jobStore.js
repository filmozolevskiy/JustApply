/** In-memory job list for the Kanban Dashboard. */

let _jobs = [];

export function getJobs() {
  return _jobs;
}

export function setJobs(jobs) {
  _jobs = Array.isArray(jobs) ? [...jobs] : [];
}

export function findJob(id) {
  return _jobs.find((j) => j.id === id);
}

export function updateJob(id, job) {
  const idx = _jobs.findIndex((j) => j.id === id);
  if (idx !== -1) {
    _jobs[idx] = job;
  }
}

export function upsertJob(job) {
  const idx = _jobs.findIndex((j) => j.id === job.id);
  if (idx !== -1) {
    _jobs[idx] = job;
  } else {
    _jobs.unshift(job);
  }
}

export function removeJob(id) {
  _jobs = _jobs.filter((j) => j.id !== id);
}

export function addJob(job) {
  _jobs.unshift(job);
}

export function hasJobMatching(title, company) {
  return _jobs.some((j) => j.title === title && j.company === company);
}

/** Add search-stream jobs that are not already on the board. Returns count added. */
export function integrateIncomingJobs(incoming) {
  if (!Array.isArray(incoming) || incoming.length === 0) {
    return 0;
  }
  let added = 0;
  for (const newJob of incoming) {
    const exists = newJob.id
      ? Boolean(findJob(newJob.id))
      : hasJobMatching(newJob.title, newJob.company);
    if (!exists) {
      addJob(newJob);
      added += 1;
    }
  }
  return added;
}
