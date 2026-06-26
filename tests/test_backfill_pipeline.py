import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
from src.core.batch_evaluation import BATCH_CHUNK_SIZE, MAX_IN_FLIGHT_BATCHES
from src.pipelines import run_backfill_pipeline
from src.service.just_apply import backfill_unevaluated_jobs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "general_cv.md").write_text("# General CV\nQA and delivery experience.")
    import src.core.matcher as matcher_module
    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))
    return db_path


def _seed_unevaluated(db_path, status="scraped", **overrides):
    job = {
        "title": "QA Engineer",
        "company": "Acme",
        "description": "Need Python and Playwright.",
        "matchScore": 0,
        "matchType": "",
        "shouldProceed": False,
        "remoteType": "in_office",
        "seniority": "",
        "status": status,
    }
    job.update(overrides)
    return database.add_job(job, db_path=str(db_path))


@pytest.mark.asyncio
async def test_empty_db_returns_zero_counts(tmp_db):
    result = await run_backfill_pipeline(log_func=None, db_path=str(tmp_db))
    assert result == {"total": 0, "batches_submitted": 0, "jobs_submitted": 0}


@pytest.mark.asyncio
async def test_get_unevaluated_jobs_excludes_evaluated(tmp_db):
    _seed_unevaluated(tmp_db)
    evaluated_job = {
        "title": "Dev",
        "company": "Corp",
        "matchType": "match",
        "matchScore": 85,
        "status": "scraped",
    }
    database.add_job(evaluated_job, db_path=str(tmp_db))

    jobs = database.get_unevaluated_jobs(db_path=str(tmp_db))
    assert len(jobs) == 1
    assert jobs[0].matchType == ""


@pytest.mark.asyncio
async def test_backfill_submits_batch_jobs(tmp_db, monkeypatch):
    job_id = _seed_unevaluated(tmp_db, status="scraped")
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "src.core.batch_evaluation._submit_jsonl_batch",
        lambda *_args, **_kwargs: ("batches/backfill-1", "JOB_STATE_PENDING"),
    )

    result = await run_backfill_pipeline(
        allowed_remote_types=["remote"],
        log_func=None,
        db_path=str(tmp_db),
    )

    assert result["total"] == 1
    assert result["batches_submitted"] == 1
    assert result["jobs_submitted"] == 1
    batches = database.list_batch_jobs(db_path=str(tmp_db))
    assert len(batches) == 1
    assert batches[0]["kind"] == "backfill"
    assert batches[0]["jobIds"] == [job_id]
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.matchType == ""
    assert job.status == "scraped"


@pytest.mark.asyncio
async def test_backfill_chunks_at_100(tmp_db, monkeypatch):
    for i in range(250):
        _seed_unevaluated(
            tmp_db,
            title=f"Job {i}",
            company=f"Co {i}",
            link=f"https://example.com/{i}",
        )

    submit_calls = []

    def fake_submit(*_args, **_kwargs):
        submit_calls.append(1)
        return (f"batches/backfill-{len(submit_calls)}", "JOB_STATE_PENDING")

    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr("src.core.batch_evaluation._submit_jsonl_batch", fake_submit)

    result = await run_backfill_pipeline(db_path=str(tmp_db))

    assert result["total"] == 250
    assert result["batches_submitted"] == 3
    assert result["jobs_submitted"] == 250
    assert len(submit_calls) == 3


@pytest.mark.asyncio
async def test_backfill_in_flight_cap_without_wait(tmp_db, monkeypatch):
    chunk_count = MAX_IN_FLIGHT_BATCHES + 1
    jobs_per_chunk = BATCH_CHUNK_SIZE
    total_jobs = chunk_count * jobs_per_chunk
    for i in range(total_jobs):
        _seed_unevaluated(
            tmp_db,
            title=f"Job {i}",
            company=f"Co {i}",
            link=f"https://example.com/{i}",
        )

    submit_calls = []

    def fake_submit(*_args, **_kwargs):
        submit_calls.append(1)
        return (f"batches/backfill-{len(submit_calls)}", "JOB_STATE_PENDING")

    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr("src.core.batch_evaluation._submit_jsonl_batch", fake_submit)

    result = await run_backfill_pipeline(db_path=str(tmp_db), wait=False)

    assert result["total"] == total_jobs
    assert result["batches_submitted"] == MAX_IN_FLIGHT_BATCHES
    assert result["jobs_submitted"] == MAX_IN_FLIGHT_BATCHES * jobs_per_chunk
    assert result["chunks_remaining"] == 1
    assert len(submit_calls) == MAX_IN_FLIGHT_BATCHES


@pytest.mark.asyncio
async def test_backfill_wait_submits_all_chunks(tmp_db, monkeypatch):
    chunk_count = MAX_IN_FLIGHT_BATCHES + 1
    jobs_per_chunk = BATCH_CHUNK_SIZE
    total_jobs = chunk_count * jobs_per_chunk
    for i in range(total_jobs):
        _seed_unevaluated(
            tmp_db,
            title=f"Job {i}",
            company=f"Co {i}",
            link=f"https://example.com/{i}",
        )

    batch_counter = {"n": 0}

    def fake_submit(*_args, **_kwargs):
        batch_counter["n"] += 1
        return (f"batches/backfill-{batch_counter['n']}", "JOB_STATE_PENDING")

    async def fake_collect(batch_row, **kwargs):
        database.update_batch_job(
            batch_row["id"],
            {"state": "JOB_STATE_SUCCEEDED"},
            db_path=str(tmp_db),
        )
        from src.core.batch_poller import CollectResult
        return CollectResult(state="JOB_STATE_SUCCEEDED", terminal=True)

    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr("src.core.batch_evaluation._submit_jsonl_batch", fake_submit)
    monkeypatch.setattr("src.core.batch_evaluation.BACKFILL_POLL_SLEEP_SECONDS", 0)
    monkeypatch.setattr("src.core.batch_poller.collect_batch_results", fake_collect)

    result = await run_backfill_pipeline(db_path=str(tmp_db), wait=True)

    assert result["batches_submitted"] == chunk_count
    assert result["jobs_submitted"] == total_jobs
    assert result["chunks_remaining"] == 0
    assert batch_counter["n"] == chunk_count


@pytest.mark.asyncio
async def test_already_evaluated_jobs_not_included(tmp_db, monkeypatch):
    _seed_unevaluated(tmp_db)
    database.add_job(
        {"title": "Dev", "company": "Corp", "matchType": "match", "matchScore": 90},
        db_path=str(tmp_db),
    )

    submit_mock = MagicMock(return_value=("batches/x", "JOB_STATE_PENDING"))
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr("src.core.batch_evaluation._submit_jsonl_batch", submit_mock)

    result = await run_backfill_pipeline(db_path=str(tmp_db))

    assert result["total"] == 1
    assert submit_mock.call_count == 1


@pytest.mark.asyncio
async def test_service_backfill_calls_pipeline(tmp_db, monkeypatch):
    _seed_unevaluated(tmp_db, status="scraped")
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "src.core.batch_evaluation._submit_jsonl_batch",
        lambda *_args, **_kwargs: ("batches/backfill-1", "JOB_STATE_PENDING"),
    )

    result = await backfill_unevaluated_jobs(
        allowed_remote_types=["remote"],
        db_path=str(tmp_db),
    )

    assert result["total"] == 1
    assert result["batches_submitted"] == 1
