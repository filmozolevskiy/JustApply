import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
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


def _make_evaluation(remote_type="remote", score=80, match_type="match"):
    return {
        "matchScore": score,
        "matchType": match_type,
        "shouldProceed": score >= 75,
        "strengths": ["Python"],
        "gaps": [],
        "remoteType": remote_type,
        "seniority": "mid",
        "summary": "Strong QA background.",
        "isRecruiter": False,
        "salary": "",
    }


@pytest.mark.asyncio
async def test_empty_db_returns_zero_counts(tmp_db):
    result = await run_backfill_pipeline(log_func=None)
    assert result == {"total": 0, "evaluated": 0, "attribute_rejected": 0, "errors": 0}


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
async def test_remote_job_found_kept_as_found(tmp_db):
    job_id = _seed_unevaluated(tmp_db, status="found")
    evaluation = _make_evaluation(remote_type="remote", score=80)
    logs = []

    with patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[evaluation])):
        result = await run_backfill_pipeline(
            allowed_remote_types=["remote"],
            log_func=lambda msg, level="info": logs.append(msg),
        )

    assert result["evaluated"] == 1
    assert result["attribute_rejected"] == 0
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "scraped"
    assert job.matchScore == 80
    assert job.matchType == "match"
    assert job.remoteType == "remote"


@pytest.mark.asyncio
async def test_non_remote_found_job_moved_to_rejected(tmp_db):
    job_id = _seed_unevaluated(tmp_db, status="found")
    evaluation = _make_evaluation(remote_type="in_office", score=85)

    with patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[evaluation])):
        result = await run_backfill_pipeline(allowed_remote_types=["remote"])

    assert result["attribute_rejected"] == 1
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.matchScore == 85


@pytest.mark.asyncio
async def test_non_remote_rejected_job_stays_rejected(tmp_db):
    job_id = _seed_unevaluated(tmp_db, status="rejected")
    evaluation = _make_evaluation(remote_type="hybrid", score=70)

    with patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[evaluation])):
        result = await run_backfill_pipeline(allowed_remote_types=["remote"])

    assert result["attribute_rejected"] == 1
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.matchScore == 70


@pytest.mark.asyncio
async def test_evaluation_failure_counted_as_error(tmp_db):
    _seed_unevaluated(tmp_db, status="found")

    with patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[None])):
        result = await run_backfill_pipeline(allowed_remote_types=["remote"])

    assert result["errors"] == 1
    assert result["evaluated"] == 0


@pytest.mark.asyncio
async def test_multiple_jobs_batched_correctly(tmp_db):
    for i in range(20):
        _seed_unevaluated(tmp_db, title=f"Job {i}", company=f"Co {i}", link=f"https://example.com/{i}")

    evaluations = [_make_evaluation(remote_type="remote", score=80)] * 20
    batch_calls = []

    async def fake_batch(jobs, resume, log_f):
        batch_calls.append(len(jobs))
        return evaluations[: len(jobs)]

    with patch("src.pipelines.evaluate_jobs_batch", side_effect=fake_batch):
        result = await run_backfill_pipeline(allowed_remote_types=["remote"])

    assert result["total"] == 20
    assert result["evaluated"] == 20
    assert len(batch_calls) == 2  # 15 + 5 with BATCH_SIZE=15
    assert batch_calls[0] == 15
    assert batch_calls[1] == 5


@pytest.mark.asyncio
async def test_already_evaluated_jobs_not_included(tmp_db):
    _seed_unevaluated(tmp_db)
    database.add_job(
        {"title": "Dev", "company": "Corp", "matchType": "match", "matchScore": 90},
        db_path=str(tmp_db),
    )

    batch_calls = []

    async def fake_batch(jobs, resume, log_f):
        batch_calls.append([j["title"] for j in jobs])
        return [_make_evaluation()] * len(jobs)

    with patch("src.pipelines.evaluate_jobs_batch", side_effect=fake_batch):
        result = await run_backfill_pipeline(allowed_remote_types=["remote"])

    assert result["total"] == 1
    assert all("QA Engineer" in call for call in batch_calls)


@pytest.mark.asyncio
async def test_service_backfill_calls_pipeline(tmp_db):
    _seed_unevaluated(tmp_db, status="found")
    evaluation = _make_evaluation(remote_type="remote", score=80)

    with patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[evaluation])):
        result = await backfill_unevaluated_jobs(allowed_remote_types=["remote"])

    assert result["total"] == 1
    assert result["evaluated"] == 1
