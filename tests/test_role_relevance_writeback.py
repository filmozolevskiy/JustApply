"""Role Relevance write-back and collect seams."""

import json
from unittest.mock import MagicMock

import pytest
from src import db as database
from src.core.batch_poller import (
    POISON_MAX_ATTEMPTS,
    collect_batch_results,
    write_back_job_evaluation,
)
from src.db import batch_jobs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    return db_path


def _seed_scraped_job(db_path, **overrides):
    job = {
        "title": "QA Engineer",
        "company": "Acme",
        "description": "Need Python.",
        "matchScore": 0,
        "matchType": "",
        "shouldProceed": False,
        "remoteType": "remote",
        "seniority": "mid",
        "status": "scraped",
    }
    job.update(overrides)
    return database.add_job(job, db_path=str(db_path))


def _evaluation(remote_type="remote", score=82, employment_type="Full-time"):
    return {
        "matchScore": score,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Python"],
        "gaps": [],
        "remoteType": remote_type,
        "seniority": "mid",
        "employmentType": employment_type,
        "summary": "Strong QA fit.",
        "isRecruiter": False,
        "salary": "",
    }


def test_write_back_role_relevant_false_rejects_as_role_filtered(tmp_db):
    job_id = _seed_scraped_job(tmp_db, title="Software Engineer")
    evaluation = _evaluation()
    evaluation["roleRelevant"] = False
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    assert outcome == "role_filtered"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.roleFiltered is True
    assert job.roleFilteredReason == "Searched QA vs Software Engineer"
    activity = [entry.message for entry in job.activityLog]
    assert not any("Role Relevance" in message for message in activity)


@pytest.mark.parametrize("role_relevant", [True, None, "omitted", "junk"])
def test_write_back_role_relevant_pass_runs_attribute_gate(tmp_db, role_relevant):
    job_id = _seed_scraped_job(tmp_db)
    evaluation = _evaluation()
    if role_relevant == "omitted":
        pass
    elif role_relevant == "junk":
        evaluation["roleRelevant"] = "maybe"
    else:
        evaluation["roleRelevant"] = role_relevant
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.roleFiltered is False
    assert job.roleFilteredReason == ""


def test_write_back_dual_fail_counts_only_as_role_filtered(tmp_db):
    job_id = _seed_scraped_job(tmp_db, title="Backend Developer", remoteType="in_office")
    evaluation = _evaluation(remote_type="in_office")
    evaluation["roleRelevant"] = False
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    assert outcome == "role_filtered"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.roleFiltered is True


def test_write_back_blank_query_skips_role_relevance(tmp_db):
    job_id = _seed_scraped_job(tmp_db, title="Software Engineer")
    evaluation = _evaluation()
    evaluation["roleRelevant"] = False
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="  ",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.roleFiltered is False


def test_write_back_mock_eval_skips_role_relevance(tmp_db):
    job_id = _seed_scraped_job(tmp_db, title="Software Engineer")
    evaluation = _evaluation()
    evaluation["roleRelevant"] = False
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="QA",
        skip_role_relevance=True,
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.roleFiltered is False


def _build_fake_client(result_jsonl: str):
    client = MagicMock()
    batch_job = MagicMock()
    batch_job.state.name = "JOB_STATE_SUCCEEDED"
    batch_job.dest.file_name = "files/result.jsonl"
    client.batches.get.return_value = batch_job
    client.files.download.return_value = result_jsonl.encode("utf-8")
    return client


def _malformed_result_line(job_id: int) -> str:
    return json.dumps({"key": str(job_id), "error": {"message": "boom"}}) + "\n"


@pytest.mark.asyncio
async def test_collect_batch_results_role_filtered_from_batch_query(tmp_db):
    job_id = _seed_scraped_job(tmp_db, title="Product Software Engineer")
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-role-filter",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    evaluation = _evaluation()
    evaluation["roleRelevant"] = False
    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(evaluation)}]}}
            ]
        },
    }
    client = _build_fake_client(json.dumps(result_line) + "\n")
    logs = []

    result = await collect_batch_results(
        batch_row,
        client=client,
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    assert result.matched == 0
    assert result.role_filtered == 1
    assert result.attribute_filtered == 0
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.roleFiltered is True
    summary = next(msg for level, msg in logs if level == "summary")
    assert summary == (
        "Batch chunk completed: 0 matched, 0 attribute-filtered, "
        "1 role-filtered, 0 fallback-rejected, 0 failed, 0 unclassified"
    )
    assert not any("job id=" in msg and "Role" in msg for _level, msg in logs)


@pytest.mark.asyncio
async def test_collect_unclassified_fallback_does_not_role_filter(tmp_db):
    job_id = _seed_scraped_job(
        tmp_db,
        title="Software Engineer",
        remoteType="remote",
        seniority="mid",
    )
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-unclassified-skip-role",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    client = _build_fake_client(_malformed_result_line(job_id))

    for _ in range(POISON_MAX_ATTEMPTS - 1):
        await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))

    result = await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))

    assert result.role_filtered == 0
    assert result.unclassified == 1
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.unclassified is True
    assert job.roleFiltered is False


def test_jobs_api_returns_role_filtered_fields(tmp_db, monkeypatch):
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.web.server import app

    monkeypatch.setattr(_db_connection, "DB_PATH", str(tmp_db))
    job_id = _seed_scraped_job(tmp_db, title="Software Engineer")
    evaluation = _evaluation()
    evaluation["roleRelevant"] = False
    write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        search_query="QA",
        db_path=str(tmp_db),
    )
    client = TestClient(app)
    listing = client.get("/api/jobs?archived=all").json()
    found = next(j for j in listing if j["id"] == job_id)
    assert found["roleFiltered"] is True
    assert found["roleFilteredReason"] == "Searched QA vs Software Engineer"
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["roleFiltered"] is True
    assert detail["roleFilteredReason"] == "Searched QA vs Software Engineer"
