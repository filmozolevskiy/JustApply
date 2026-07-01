import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
from src.db import batch_jobs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    return db_path


def test_create_and_get_batch_job_round_trip(tmp_db):
    row = batch_jobs.create_batch_job(
        batch_name="batches/abc123",
        display_name="justapply-search-1",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[1, 2, 3],
        db_path=str(tmp_db),
    )

    assert row["id"] == 1
    assert row["batchName"] == "batches/abc123"
    assert row["displayName"] == "justapply-search-1"
    assert row["state"] == "JOB_STATE_PENDING"
    assert row["kind"] == "search"
    assert row["jobIds"] == [1, 2, 3]
    assert row["lastPolledAt"] is None
    assert row["resultFileName"] is None

    fetched = batch_jobs.get_batch_job(row["id"], db_path=str(tmp_db))
    assert fetched == row

    by_name = batch_jobs.get_batch_job_by_name("batches/abc123", db_path=str(tmp_db))
    assert by_name == row


def test_batch_name_uniqueness_enforced(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/dup",
        display_name="first",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[1],
        db_path=str(tmp_db),
    )

    with pytest.raises(Exception):
        batch_jobs.create_batch_job(
            batch_name="batches/dup",
            display_name="second",
            state="JOB_STATE_PENDING",
            kind="backfill",
            job_ids=[2],
            db_path=str(tmp_db),
        )


def test_update_batch_job_persists_fields(tmp_db):
    row = batch_jobs.create_batch_job(
        batch_name="batches/update-me",
        display_name="before",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[10],
        db_path=str(tmp_db),
    )

    updated = batch_jobs.update_batch_job(
        row["id"],
        {
            "state": "JOB_STATE_SUCCEEDED",
            "lastPolledAt": "2026-06-26T12:00:00+00:00",
            "resultFileName": "files/result.jsonl",
            "jobIds": [10, 11],
        },
        db_path=str(tmp_db),
    )

    assert updated["state"] == "JOB_STATE_SUCCEEDED"
    assert updated["lastPolledAt"] == "2026-06-26T12:00:00+00:00"
    assert updated["resultFileName"] == "files/result.jsonl"
    assert updated["jobIds"] == [10, 11]


def test_in_flight_job_ids_exclude_terminal_states(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/running",
        display_name="running",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[1, 2],
        db_path=str(tmp_db),
    )
    batch_jobs.create_batch_job(
        batch_name="batches/done",
        display_name="done",
        state="JOB_STATE_SUCCEEDED",
        kind="search",
        job_ids=[3],
        db_path=str(tmp_db),
    )

    assert batch_jobs.get_in_flight_job_ids(db_path=str(tmp_db)) == {1, 2}
    assert len(batch_jobs.list_in_flight_batch_jobs(db_path=str(tmp_db))) == 1
    assert len(batch_jobs.list_batch_jobs(db_path=str(tmp_db))) == 2
