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

export function removeJob(id) {
  _jobs = _jobs.filter((j) => j.id !== id);
}

export function addJob(job) {
  _jobs.unshift(job);
}

export function hasJobMatching(title, company) {
  return _jobs.some((j) => j.title === title && j.company === company);
}
