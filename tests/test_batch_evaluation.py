import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.core.batch_evaluation import (
    BATCH_CHUNK_SIZE,
    build_batch_jsonl,
    build_batch_request_line,
    chunk_jobs,
    submit_batch_evaluation,
)


def test_build_batch_request_line_uses_job_id_key_and_json_mime():
    line = build_batch_request_line(
        42,
        "# Resume",
        {"title": "QA", "company": "Acme", "description": "Test role"},
    )

    assert line["key"] == "42"
    assert line["request"]["generation_config"]["response_mime_type"] == "application/json"
    assert "QA" in line["request"]["contents"][0]["parts"][0]["text"]
    assert "Acme" in line["request"]["contents"][0]["parts"][0]["text"]


def test_build_batch_jsonl_one_line_per_job():
    jobs = [
        {"id": 1, "title": "A", "company": "Co", "description": "Desc"},
        {"id": 2, "title": "B", "company": "Co", "description": "Desc"},
    ]
    jsonl = build_batch_jsonl(jobs, "# Resume")
    lines = [line for line in jsonl.strip().splitlines() if line]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["key"] == "1"


def test_chunk_jobs_splits_at_100():
    jobs = [{"id": i} for i in range(250)]
    chunks = chunk_jobs(jobs, chunk_size=BATCH_CHUNK_SIZE)
    assert len(chunks) == 3
    assert len(chunks[0]) == 100
    assert len(chunks[1]) == 100
    assert len(chunks[2]) == 50


@pytest.mark.asyncio
async def test_submit_batch_evaluation_persists_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "src.core.batch_evaluation._submit_jsonl_batch",
        lambda *_args, **_kwargs: ("batches/test-1", "JOB_STATE_PENDING"),
    )

    from src import db as database

    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))

    jobs = [{"id": i, "title": f"Job {i}", "company": "Co", "description": "Desc"} for i in range(1, 4)]
    created = await submit_batch_evaluation(jobs, "# Resume", kind="search", db_path=str(db_path))

    assert len(created) == 1
    assert created[0]["batchName"] == "batches/test-1"
    assert created[0]["jobIds"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_submit_batch_evaluation_skips_in_flight_job_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    submit_mock = MagicMock(return_value=("batches/test-2", "JOB_STATE_PENDING"))
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr("src.core.batch_evaluation._submit_jsonl_batch", submit_mock)

    from src import db as database
    from src.db import batch_jobs

    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    batch_jobs.create_batch_job(
        batch_name="batches/existing",
        display_name="existing",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[1],
        db_path=str(db_path),
    )

    jobs = [
        {"id": 1, "title": "Already in flight", "company": "Co", "description": "Desc"},
        {"id": 2, "title": "New job", "company": "Co", "description": "Desc"},
    ]
    created = await submit_batch_evaluation(jobs, "# Resume", kind="search", db_path=str(db_path))

    assert len(created) == 1
    assert created[0]["jobIds"] == [2]
    assert submit_mock.call_count == 1
