"""Enrichment status transitions — single owner for enriching lifecycle."""

from ... import db as database

ENRICHMENT_SOURCE_STATUSES = frozenset({"sourced", "enriched"})

# Prior lane to restore when enrichment aborts before completion.
_enrichment_prior_status: dict[int, str] = {}


def begin_enrichment(job_id: int, db_path=None) -> dict | None:
    """Move a job to enriching. Idempotent when already enriching."""
    job = database.get_job(job_id, db_path)
    if not job:
        return None

    status = job.status
    if status == "enriching":
        return job
    if status not in ENRICHMENT_SOURCE_STATUSES:
        return None

    _enrichment_prior_status[job_id] = status
    return database.start_enrichment(job_id, db_path)


def abort_enrichment(job_id: int, db_path=None) -> dict | None:
    """Revert an in-flight enrichment to the lane it started from."""
    prior = _enrichment_prior_status.pop(job_id, None)
    job = database.get_job(job_id, db_path)
    if not job:
        return None
    if job.status != "enriching":
        return job
    if prior is None:
        prior = "sourced"
    return database.update_job_status(job_id, prior, db_path)


def clear_enrichment_prior(job_id: int) -> None:
    """Drop stored prior status after enrichment completes."""
    _enrichment_prior_status.pop(job_id, None)
