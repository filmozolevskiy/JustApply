"""Enrichment status transitions — single owner for enrichment lifecycle."""

from ... import db as database

ENRICHMENT_SOURCE_STATUSES = frozenset({"scraped", "matched", "accepted"})

# Prior lane to restore when enrichment aborts before completion.
_enrichment_prior_status: dict[int, str] = {}


def begin_enrichment(job_id: int, db_path=None) -> dict | None:
    """Move a Found job to Accepted and record prior status for abort."""
    job = database.get_job(job_id, db_path)
    if not job:
        return None

    status = job.status
    if status == "accepted" and job_id in _enrichment_prior_status:
        # Already in progress from begin_enrichment
        return job
    if status not in ENRICHMENT_SOURCE_STATUSES:
        return None

    _enrichment_prior_status[job_id] = status
    if status != "accepted":
        # Found → Accepted before enriching
        database.update_job_status(job_id, "accepted", db_path)
    return database.get_job(job_id, db_path)


def abort_enrichment(job_id: int, db_path=None) -> dict | None:
    """Revert an aborted enrichment. Accepted jobs stay Accepted."""
    _enrichment_prior_status.pop(job_id, None)
    job = database.get_job(job_id, db_path)
    return job


def clear_enrichment_prior(job_id: int) -> None:
    """Drop stored prior status after enrichment completes."""
    _enrichment_prior_status.pop(job_id, None)
