import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
from src.core.batch_poller import (
    collect_batch_results,
    is_due_for_poll,
    poll_cadence_seconds,
    write_back_job_evaluation,
)
from src.db import batch_jobs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    return db_path


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (0, 60),
        (600, 60),
        (601, 120),
        (2400, 120),
        (2401, 300),
        (10800, 300),
        (10801, 900),
        (172800, 900),
    ],
)
def test_poll_cadence_seconds_table(age_seconds, expected):
    assert poll_cadence_seconds(age_seconds) == expected


def test_is_due_for_poll_respects_cadence():
    submitted = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
    batch = {
        "submittedAt": submitted.isoformat(),
        "lastPolledAt": None,
    }
    assert is_due_for_poll(batch, now=submitted.replace(minute=0, second=30)) is False
    assert is_due_for_poll(batch, now=submitted.replace(minute=1, second=1)) is True


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


def _evaluation(remote_type="remote", score=82):
    return {
        "matchScore": score,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Python"],
        "gaps": [],
        "remoteType": remote_type,
        "seniority": "mid",
        "summary": "Strong QA fit.",
        "isRecruiter": False,
        "salary": "",
    }


def test_write_back_moves_scraped_to_matched(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    outcome = write_back_job_evaluation(
        job_id,
        _evaluation(),
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.matchScore == 82
    assert job.matchType == "match"


def test_write_back_gate_fail_moves_to_rejected(tmp_db):
    job_id = _seed_scraped_job(tmp_db, remoteType="in_office")
    outcome = write_back_job_evaluation(
        job_id,
        _evaluation(remote_type="in_office"),
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    assert outcome == "rejected"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"


def _build_fake_client(result_jsonl: str):
    client = MagicMock()
    batch_job = MagicMock()
    batch_job.state.name = "JOB_STATE_SUCCEEDED"
    batch_job.dest.file_name = "files/result.jsonl"
    client.batches.get.return_value = batch_job
    client.files.download.return_value = result_jsonl.encode("utf-8")
    return client


@pytest.mark.asyncio
async def test_collect_batch_results_writes_back_and_updates_batch_row(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-success",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )

    evaluation = _evaluation()
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

    assert result.terminal is True
    assert result.matched == 1
    assert result.rejected == 0

    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.matchScore == 82

    updated_batch = batch_jobs.get_batch_job(batch_row["id"], db_path=str(tmp_db))
    assert updated_batch["state"] == "JOB_STATE_SUCCEEDED"
    assert updated_batch["lastPolledAt"] is not None
    assert updated_batch["resultFileName"] == "files/result.jsonl"
    assert any("Batch chunk completed" in msg for _level, msg in logs)


@pytest.mark.asyncio
async def test_collect_batch_results_attribute_reject(tmp_db):
    job_id = _seed_scraped_job(tmp_db, remoteType="in_office")
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-reject",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )

    evaluation = _evaluation(remote_type="in_office")
    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(evaluation)}]}}
            ]
        },
    }
    client = _build_fake_client(json.dumps(result_line) + "\n")

    result = await collect_batch_results(
        batch_row,
        client=client,
        db_path=str(tmp_db),
    )

    assert result.matched == 0
    assert result.rejected == 1
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"


@pytest.mark.asyncio
async def test_poll_in_flight_skips_batches_not_due(tmp_db, monkeypatch):
    from src.core import batch_poller

    job_id = _seed_scraped_job(tmp_db)
    submitted = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
    batch_jobs.create_batch_job(
        batch_name="batches/not-due",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        submitted_at=submitted.isoformat(),
        db_path=str(tmp_db),
    )

    called = []

    async def fake_collect(*args, **kwargs):
        called.append(True)
        return batch_poller.CollectResult(state="JOB_STATE_RUNNING")

    monkeypatch.setattr(batch_poller, "collect_batch_results", fake_collect)

    now = submitted.replace(second=30)
    await batch_poller.poll_in_flight_batches(db_path=str(tmp_db), now=now)
    assert called == []


@pytest.mark.asyncio
async def test_collect_batch_results_terminal_failure_leaves_jobs_scraped(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-failed",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        db_path=str(tmp_db),
    )

    client = MagicMock()
    batch_job = MagicMock()
    batch_job.state.name = "JOB_STATE_FAILED"
    batch_job.dest = None
    client.batches.get.return_value = batch_job

    logs = []
    result = await collect_batch_results(
        batch_row,
        client=client,
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append(msg),
    )

    assert result.terminal is True
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "scraped"
    assert any("JOB_STATE_FAILED" in msg for msg in logs)
