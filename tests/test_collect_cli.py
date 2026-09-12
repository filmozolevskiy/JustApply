import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src import db as database
from src.cli.cli import run_collect
from src.core.batch_poller import reset_round_accumulator, run_batch_collection
from src.db import batch_jobs
from src.service import collect_batch_evaluation_results


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    reset_round_accumulator()
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

def _evaluation(score=82):
    return {
        "matchScore": score,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Python"],
        "gaps": [],
        "remoteType": "remote",
        "seniority": "mid",
        "summary": "Strong QA fit.",
        "isRecruiter": False,
        "salary": "",
    }

def _build_fake_client(result_jsonl: str):
    client = MagicMock()
    batch_job = MagicMock()
    batch_job.state.name = "JOB_STATE_SUCCEEDED"
    batch_job.dest.file_name = "files/result.jsonl"
    client.batches.get.return_value = batch_job
    client.files.download.return_value = result_jsonl.encode("utf-8")
    return client

@pytest.mark.asyncio
async def test_collect_once_writes_back_with_fake_client(tmp_db, monkeypatch):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/collect-once",
        display_name="collect-once",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )

    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(_evaluation())}]}}
            ]
        },
    }
    fake_client = _build_fake_client(json.dumps(result_line) + "\n")
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: fake_client)

    submit_mock = MagicMock()
    monkeypatch.setattr("src.core.batch_evaluation.submit_batch_evaluation", submit_mock)

    result = await run_batch_collection(db_path=str(tmp_db))

    assert result["batches_polled"] == 1
    assert result["matched"] == 1
    assert result["in_flight_remaining"] == 0
    submit_mock.assert_not_called()

    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.matchScore == 82

@pytest.mark.asyncio
async def test_collect_works_while_evaluation_lock_active(tmp_db, monkeypatch):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/lock-active",
        display_name="lock-active",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )

    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(_evaluation())}]}}
            ]
        },
    }
    fake_client = _build_fake_client(json.dumps(result_line) + "\n")
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: fake_client)

    result = await run_collect(wait=False)

    assert result["matched"] == 1
    assert result["in_flight_remaining"] == 0

@pytest.mark.asyncio
async def test_collect_wait_loops_until_terminal(tmp_db, monkeypatch):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/wait-loop",
        display_name="wait-loop",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    pending_job = MagicMock()
    pending_job.state.name = "JOB_STATE_RUNNING"
    pending_job.dest = None

    succeeded_job = MagicMock()
    succeeded_job.state.name = "JOB_STATE_SUCCEEDED"
    succeeded_job.dest.file_name = "files/result.jsonl"

    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(_evaluation())}]}}
            ]
        },
    }

    client = MagicMock()
    client.batches.get.side_effect = [pending_job, succeeded_job]
    client.files.download.return_value = (json.dumps(result_line) + "\n").encode("utf-8")
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)
    monkeypatch.setattr("src.core.batch_poller.is_due_for_poll", lambda *_args, **_kwargs: True)

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("src.core.batch_poller.asyncio.sleep", fake_sleep)

    result = await collect_batch_evaluation_results(
        wait=True,
        db_path=str(tmp_db),
    )

    assert result["matched"] == 1
    assert result["in_flight_remaining"] == 0
    assert client.batches.get.call_count == 2
    assert sleep_calls

@pytest.mark.asyncio
async def test_collect_once_with_no_in_flight_batches(tmp_db):
    result = await run_batch_collection(db_path=str(tmp_db))

    assert result["batches_polled"] == 0
    assert result["matched"] == 0
    assert result["attribute_filtered"] == 0
    assert result["role_filtered"] == 0
    assert result["fallback_rejected"] == 0
    assert result["in_flight_remaining"] == 0


@pytest.mark.asyncio
async def test_collect_cli_footer_prints_split_rejection_counters(tmp_db, monkeypatch, capsys):
    matched_id = _seed_scraped_job(tmp_db)
    filtered_id = _seed_scraped_job(tmp_db, remoteType="in_office", title="Office QA")
    batch_jobs.create_batch_job(
        batch_name="batches/collect-footer",
        display_name="collect-footer",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[matched_id, filtered_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )

    lines = [
        {
            "key": str(matched_id),
            "response": {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(_evaluation())}]}}
                ]
            },
        },
        {
            "key": str(filtered_id),
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            **_evaluation(),
                                            "remoteType": "in_office",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        },
    ]
    fake_client = _build_fake_client(
        "\n".join(json.dumps(line) for line in lines) + "\n"
    )
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: fake_client)

    result = await run_collect(wait=False)
    captured = capsys.readouterr()

    assert result["matched"] == 1
    assert result["attribute_filtered"] == 1
    assert result["role_filtered"] == 0
    assert result["fallback_rejected"] == 0
    assert "Attribute-filtered: 1" in captured.out
    assert "Role-filtered: 0" in captured.out
    assert "Fallback-rejected: 0" in captured.out
    assert "Rejected:" not in captured.out
    assert any(
        "Batch chunk completed: 1 matched, 1 attribute-filtered, "
        "0 role-filtered, 0 fallback-rejected, 0 failed, 0 unclassified" in line
        for line in captured.err.splitlines()
    )
    assert any(
        "Evaluation round complete (search): 1 matched, 1 attribute-filtered, "
        "0 role-filtered, 0 fallback-rejected, 0 failed, 0 unclassified" in line
        for line in captured.err.splitlines()
    )
    assert "Attribute mismatch" not in captured.err


@pytest.mark.asyncio
async def test_collect_wait_prints_round_summary_after_chunk(
    tmp_db, monkeypatch, capsys
):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/collect-wait-round",
        display_name="collect-wait-round",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    pending_job = MagicMock()
    pending_job.state.name = "JOB_STATE_RUNNING"
    pending_job.dest = None

    succeeded_job = MagicMock()
    succeeded_job.state.name = "JOB_STATE_SUCCEEDED"
    succeeded_job.dest.file_name = "files/result.jsonl"

    result_line = {
        "key": str(job_id),
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(_evaluation())}]}}
            ]
        },
    }

    client = MagicMock()
    client.batches.get.side_effect = [pending_job, succeeded_job]
    client.files.download.return_value = (json.dumps(result_line) + "\n").encode("utf-8")
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_args, **_kwargs: True
    )

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("src.core.batch_poller.asyncio.sleep", fake_sleep)

    await run_collect(wait=True)
    err_lines = capsys.readouterr().err.splitlines()

    chunk_idx = next(i for i, line in enumerate(err_lines) if "Batch chunk completed" in line)
    round_idx = next(
        i for i, line in enumerate(err_lines) if "Evaluation round complete" in line
    )
    assert chunk_idx < round_idx
    assert (
        "Evaluation round complete (search): 1 matched, 0 attribute-filtered, "
        "0 role-filtered, 0 fallback-rejected, 0 failed, 0 unclassified"
    ) in err_lines[round_idx]
