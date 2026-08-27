import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src import db as database
from src.core.batch_poller import (
    POISON_MAX_ATTEMPTS,
    apply_unclassified_fallback,
    collect_batch_results,
    collect_in_flight_batches_once,
    handle_poison_job_failure,
    is_due_for_poll,
    poll_cadence_seconds,
    poll_in_flight_batches,
    reset_round_accumulator,
    wait_for_in_flight_collection,
    write_back_job_evaluation,
)
from src.db import batch_jobs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    reset_round_accumulator()
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
    submitted = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
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
    assert job.employmentType == "Full-time"

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


def test_write_back_employment_type_mismatch_rejected(tmp_db):
    job_id = _seed_scraped_job(tmp_db, employmentType="Full-time")
    outcome = write_back_job_evaluation(
        job_id,
        _evaluation(employment_type="Contract"),
        allowed_remote_types=["any"],
        seniorities="any",
        employment_types="Full-time",
        db_path=str(tmp_db),
    )
    assert outcome == "rejected"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.employmentType == "Contract"


def test_write_back_salary_min_rejects_when_annual_max_below(tmp_db):
    job_id = _seed_scraped_job(tmp_db, salary="$100k - $110k")
    evaluation = _evaluation()
    evaluation["salary"] = "$100,000 - $110,000"
    evaluation["postedSalary"] = {
        "period": "yearly",
        "amountMin": 100000,
        "amountMax": 110000,
        "currency": "USD",
    }
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["any"],
        seniorities="any",
        salary_min=120000,
        db_path=str(tmp_db),
    )
    assert outcome == "rejected"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.annualMax == 110000


def test_write_back_salary_min_passes_when_annual_max_reaches_min(tmp_db):
    job_id = _seed_scraped_job(tmp_db, salary="$100k - $130k")
    evaluation = _evaluation()
    evaluation["salary"] = "$100,000 - $130,000"
    evaluation["postedSalary"] = {
        "period": "yearly",
        "amountMin": 100000,
        "amountMax": 130000,
        "currency": "USD",
    }
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["any"],
        seniorities="any",
        salary_min=120000,
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.annualMax == 130000


def test_write_back_salary_min_unknown_pay_still_matches(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    evaluation = _evaluation()
    evaluation["salary"] = ""
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["any"],
        seniorities="any",
        salary_min=120000,
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.annualMax is None


def test_write_back_persists_yearly_annual_posted_salary(tmp_db):
    job_id = _seed_scraped_job(tmp_db, salary="$125k - $145k")
    evaluation = _evaluation()
    evaluation["salary"] = "$125,000 - $145,000"
    evaluation["postedSalary"] = {
        "period": "yearly",
        "amountMin": 125000,
        "amountMax": 145000,
        "currency": "USD",
    }
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.salary == "$125,000 - $145,000"
    assert job.annualMin == 125000
    assert job.annualMax == 145000
    assert job.annualCurrency == "USD"


def test_write_back_yearly_point_salary_equal_band(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    evaluation = _evaluation()
    evaluation["salary"] = "$130,000"
    evaluation["postedSalary"] = {
        "period": "yearly",
        "amountMin": 130000,
        "currency": "CAD",
    }
    write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.annualMin == 130000
    assert job.annualMax == 130000
    assert job.annualCurrency == "CAD"


def test_write_back_without_posted_salary_facts_leaves_annual_null(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    evaluation = _evaluation()
    evaluation["salary"] = "$70/hr"
    write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.salary == "$70/hr"
    assert job.annualMin is None
    assert job.annualMax is None
    assert job.annualCurrency is None


def test_write_back_hourly_posted_salary_annualizes_with_2080_default(tmp_db):
    job_id = _seed_scraped_job(tmp_db, location="Toronto, ON", salary="$70-80/hr")
    evaluation = _evaluation()
    evaluation["salary"] = "$70-80/hr"
    evaluation["postedSalary"] = {
        "period": "hourly",
        "amountMin": 70,
        "amountMax": 80,
        "currency": "USD",
    }
    outcome = write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.salary == "$70-80/hr"
    assert job.annualMin == 70 * 2080
    assert job.annualMax == 80 * 2080
    assert job.annualCurrency == "USD"


def test_write_back_multi_location_picks_job_location_band(tmp_db):
    job_id = _seed_scraped_job(
        tmp_db,
        location="New York, United States",
        salary="Toronto $100k-$120k CAD; New York $130k-$150k USD",
    )
    evaluation = _evaluation()
    evaluation["salary"] = "Toronto $100k-$120k CAD; New York $130k-$150k USD"
    evaluation["postedSalary"] = {
        "bands": [
            {
                "location": "Toronto, ON",
                "period": "yearly",
                "amountMin": 100000,
                "amountMax": 120000,
                "currency": "CAD",
            },
            {
                "location": "New York, NY",
                "period": "yearly",
                "amountMin": 130000,
                "amountMax": 150000,
                "currency": "USD",
            },
        ]
    }
    write_back_job_evaluation(
        job_id,
        evaluation,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.annualMin == 130000
    assert job.annualMax == 150000
    assert job.annualCurrency == "USD"


def _build_fake_client(result_jsonl: str):
    client = MagicMock()
    batch_job = MagicMock()
    batch_job.state.name = "JOB_STATE_SUCCEEDED"
    batch_job.dest.file_name = "files/result.jsonl"
    client.batches.get.return_value = batch_job
    client.files.download.return_value = result_jsonl.encode("utf-8")
    return client

@pytest.mark.asyncio
async def test_collect_batch_results_rejects_salary_min_from_batch_prefs(tmp_db):
    job_id = _seed_scraped_job(tmp_db, salary="$100k")
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-salary-reject",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["any"],
        search_seniorities="any",
        search_employment_types="any",
        search_salary_min=120000,
        db_path=str(tmp_db),
    )
    evaluation = _evaluation()
    evaluation["salary"] = "$100,000"
    evaluation["postedSalary"] = {
        "period": "yearly",
        "amountMin": 100000,
        "amountMax": 100000,
        "currency": "USD",
    }
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

    assert result.attribute_filtered == 1
    assert result.matched == 0
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.annualMax == 100000


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
    assert result.attribute_filtered == 0
    assert result.fallback_rejected == 0

    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.matchScore == 82

    updated_batch = batch_jobs.get_batch_job(batch_row["id"], db_path=str(tmp_db))
    assert updated_batch["state"] == "JOB_STATE_SUCCEEDED"
    assert updated_batch["lastPolledAt"] is not None
    assert updated_batch["resultFileName"] == "files/result.jsonl"
    summary_logs = [(level, msg) for level, msg in logs if "Batch chunk completed" in msg]
    assert summary_logs
    level, msg = summary_logs[0]
    assert level == "summary"
    assert msg == (
        "Batch chunk completed: 1 matched, 0 attribute-filtered, "
        "0 fallback-rejected, 0 failed, 0 unclassified"
    )
    assert not any("Attribute mismatch" in msg for _level, msg in logs)

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
    logs = []

    result = await collect_batch_results(
        batch_row,
        client=client,
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    assert result.matched == 0
    assert result.attribute_filtered == 1
    assert result.fallback_rejected == 0
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    summary = next(msg for level, msg in logs if level == "summary")
    assert summary == (
        "Batch chunk completed: 0 matched, 1 attribute-filtered, "
        "0 fallback-rejected, 0 failed, 0 unclassified"
    )
    assert not any("Attribute mismatch" in msg for _level, msg in logs)


@pytest.mark.asyncio
async def test_collect_batch_results_fallback_reject_increments_fallback_rejected(tmp_db):
    """Poison fallback gated on scraper attributes counts as fallback-rejected."""
    job_id = _seed_scraped_job(tmp_db, remoteType="in_office", seniority="mid")
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-fallback-reject",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )
    client = _build_fake_client(_malformed_result_line(job_id))
    logs = []

    for _ in range(POISON_MAX_ATTEMPTS - 1):
        await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))

    result = await collect_batch_results(
        batch_row,
        client=client,
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    assert result.attribute_filtered == 0
    assert result.fallback_rejected == 1
    assert result.unclassified == 0
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.unclassified is True
    summary = next(msg for level, msg in logs if level == "summary")
    assert summary == (
        "Batch chunk completed: 0 matched, 0 attribute-filtered, "
        "1 fallback-rejected, 0 failed, 0 unclassified"
    )
    assert not any("Attribute mismatch" in msg for _level, msg in logs)

@pytest.mark.asyncio
async def test_poll_in_flight_skips_batches_not_due(tmp_db, monkeypatch):
    from src.core import batch_poller

    job_id = _seed_scraped_job(tmp_db)
    submitted = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
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
    assert job.batchAttempts == 1
    assert any("JOB_STATE_FAILED" in msg for msg in logs)

def _malformed_result_line(job_id: int) -> str:
    return json.dumps({"key": str(job_id), "error": {"message": "bad response"}}) + "\n"

@pytest.mark.asyncio
async def test_malformed_result_increments_batch_attempts(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-malformed",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )
    client = _build_fake_client(_malformed_result_line(job_id))

    await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))

    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "scraped"
    assert job.batchAttempts == 1

@pytest.mark.asyncio
async def test_poison_job_unclassified_fallback_after_max_attempts(tmp_db):
    job_id = _seed_scraped_job(tmp_db, remoteType="remote", seniority="mid")
    batch_row = batch_jobs.create_batch_job(
        batch_name="batches/test-poison",
        display_name="test",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )
    client = _build_fake_client(_malformed_result_line(job_id))

    for attempt in range(1, POISON_MAX_ATTEMPTS):
        await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))
        job = database.get_job(job_id, db_path=str(tmp_db))
        assert job.status == "scraped"
        assert job.batchAttempts == attempt

    result = await collect_batch_results(batch_row, client=client, db_path=str(tmp_db))
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "matched"
    assert job.unclassified is True
    assert job.batchAttempts == POISON_MAX_ATTEMPTS
    assert job.matchType == "no-match"
    assert result.unclassified == 1

def test_apply_unclassified_fallback_uses_scraper_attributes(tmp_db):
    job_id = _seed_scraped_job(
        tmp_db,
        remoteType="remote",
        seniority="senior",
        employmentType="Full-time",
    )
    outcome = apply_unclassified_fallback(
        job_id,
        allowed_remote_types=["remote"],
        seniorities="senior",
        employment_types="Full-time",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.unclassified is True
    assert job.remoteType == "remote"
    assert job.seniority == "senior"
    assert job.employmentType == "Full-time"


def test_apply_unclassified_fallback_rejects_employment_type_mismatch(tmp_db):
    job_id = _seed_scraped_job(
        tmp_db,
        remoteType="remote",
        seniority="mid",
        employmentType="Contract",
    )
    outcome = apply_unclassified_fallback(
        job_id,
        allowed_remote_types=["any"],
        seniorities="any",
        employment_types="Full-time",
        db_path=str(tmp_db),
    )
    assert outcome == "rejected"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "rejected"
    assert job.unclassified is True
    assert job.employmentType == "Contract"

def test_handle_poison_job_failure_retries_before_fallback(tmp_db):
    job_id = _seed_scraped_job(tmp_db)
    for attempt in range(1, POISON_MAX_ATTEMPTS):
        outcome = handle_poison_job_failure(
            job_id,
            allowed_remote_types=["remote"],
            seniorities="any",
            db_path=str(tmp_db),
        )
        assert outcome == "retry"
        job = database.get_job(job_id, db_path=str(tmp_db))
        assert job.status == "scraped"
        assert job.batchAttempts == attempt

    outcome = handle_poison_job_failure(
        job_id,
        allowed_remote_types=["remote"],
        seniorities="any",
        db_path=str(tmp_db),
    )
    assert outcome == "matched"
    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.unclassified is True
    assert job.status == "matched"


def _success_result_line(job_id: int, evaluation: dict | None = None) -> str:
    payload = evaluation or _evaluation()
    return json.dumps(
        {
            "key": str(job_id),
            "response": {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(payload)}]}}
                ]
            },
        }
    ) + "\n"


@pytest.mark.asyncio
async def test_round_summary_aggregates_multi_chunk_search(tmp_db, monkeypatch):
    """One Evaluation Round Summary when the last in-flight batch finishes."""
    job_a = _seed_scraped_job(tmp_db, title="QA A")
    job_b = _seed_scraped_job(tmp_db, title="QA B")
    job_c = _seed_scraped_job(tmp_db, title="Office QA", remoteType="in_office")

    batch_jobs.create_batch_job(
        batch_name="batches/round-a",
        display_name="round-a",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_a, job_c],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )
    batch_jobs.create_batch_job(
        batch_name="batches/round-b",
        display_name="round-b",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_b],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    lines_a = (
        _success_result_line(job_a)
        + _success_result_line(job_c, _evaluation(remote_type="in_office"))
    )
    lines_b = _success_result_line(job_b)

    client = MagicMock()
    batch_ok = MagicMock()
    batch_ok.state.name = "JOB_STATE_SUCCEEDED"
    batch_ok.dest.file_name = "files/result.jsonl"
    client.batches.get.return_value = batch_ok
    client.files.download.side_effect = [
        lines_a.encode("utf-8"),
        lines_b.encode("utf-8"),
    ]
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_a, **_k: True
    )

    logs: list[tuple[str, str]] = []

    await poll_in_flight_batches(
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    chunk_logs = [msg for level, msg in logs if "Batch chunk completed" in msg]
    round_logs = [
        (level, msg) for level, msg in logs if "Evaluation round complete" in msg
    ]
    assert len(chunk_logs) == 2
    assert len(round_logs) == 1
    level, msg = round_logs[0]
    assert level == "summary"
    assert msg == (
        "Evaluation round complete (search): 2 matched, 1 attribute-filtered, "
        "0 fallback-rejected, 0 failed, 0 unclassified"
    )


@pytest.mark.asyncio
async def test_round_summary_waits_until_last_chunk(tmp_db, monkeypatch):
    """No round summary until every in-flight batch in the round is terminal."""
    job_a = _seed_scraped_job(tmp_db, title="QA A")
    job_b = _seed_scraped_job(tmp_db, title="QA B")

    batch_jobs.create_batch_job(
        batch_name="batches/partial-a",
        display_name="partial-a",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_a],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )
    batch_jobs.create_batch_job(
        batch_name="batches/partial-b",
        display_name="partial-b",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_b],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    pending = MagicMock()
    pending.state.name = "JOB_STATE_RUNNING"
    pending.dest = None
    succeeded = MagicMock()
    succeeded.state.name = "JOB_STATE_SUCCEEDED"
    succeeded.dest.file_name = "files/result.jsonl"

    client = MagicMock()
    # First poll: A succeeds, B still running. Second poll: B succeeds.
    client.batches.get.side_effect = [succeeded, pending, succeeded]
    client.files.download.side_effect = [
        _success_result_line(job_a).encode("utf-8"),
        _success_result_line(job_b).encode("utf-8"),
    ]
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_a, **_k: True
    )

    logs: list[tuple[str, str]] = []

    def log_func(msg, level="info"):
        logs.append((level, msg))

    await poll_in_flight_batches(db_path=str(tmp_db), log_func=log_func)
    assert not any("Evaluation round complete" in msg for _level, msg in logs)
    assert len(batch_jobs.list_in_flight_batch_jobs(db_path=str(tmp_db))) == 1

    await poll_in_flight_batches(db_path=str(tmp_db), log_func=log_func)
    round_logs = [msg for _level, msg in logs if "Evaluation round complete" in msg]
    assert round_logs == [
        "Evaluation round complete (search): 2 matched, 0 attribute-filtered, "
        "0 fallback-rejected, 0 failed, 0 unclassified"
    ]


@pytest.mark.asyncio
async def test_round_summary_labels_backfill_kind(tmp_db, monkeypatch):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/backfill-round",
        display_name="backfill-round",
        state="JOB_STATE_RUNNING",
        kind="backfill",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        db_path=str(tmp_db),
    )
    client = _build_fake_client(_success_result_line(job_id))
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)

    logs: list[tuple[str, str]] = []
    await collect_in_flight_batches_once(
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    round_msg = next(msg for level, msg in logs if "Evaluation round complete" in msg)
    assert round_msg.startswith("Evaluation round complete (backfill):")
    assert "1 matched" in round_msg


@pytest.mark.asyncio
async def test_wait_collect_emits_round_summary_after_chunks(tmp_db, monkeypatch):
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/wait-round",
        display_name="wait-round",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    pending = MagicMock()
    pending.state.name = "JOB_STATE_RUNNING"
    pending.dest = None
    succeeded = MagicMock()
    succeeded.state.name = "JOB_STATE_SUCCEEDED"
    succeeded.dest.file_name = "files/result.jsonl"

    client = MagicMock()
    client.batches.get.side_effect = [pending, succeeded]
    client.files.download.return_value = _success_result_line(job_id).encode("utf-8")
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_a, **_k: True
    )

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("src.core.batch_poller.asyncio.sleep", fake_sleep)

    logs: list[str] = []
    await wait_for_in_flight_collection(
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append(msg),
    )

    chunk_idx = next(
        i for i, msg in enumerate(logs) if "Batch chunk completed" in msg
    )
    round_idx = next(
        i for i, msg in enumerate(logs) if "Evaluation round complete" in msg
    )
    assert chunk_idx < round_idx
    assert logs[round_idx] == (
        "Evaluation round complete (search): 1 matched, 0 attribute-filtered, "
        "0 fallback-rejected, 0 failed, 0 unclassified"
    )


@pytest.mark.asyncio
async def test_round_clear_auto_retries_poison_failed_jobs(tmp_db, tmp_path, monkeypatch):
    """After Evaluation Round Summary, poison-failed Scraped jobs get a retry batch."""
    job_id = _seed_scraped_job(tmp_db)
    batch_jobs.create_batch_job(
        batch_name="batches/search-poison",
        display_name="search-poison",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[job_id],
        search_remote_types=["remote"],
        search_seniorities="mid",
        search_employment_types="Full-time",
        search_salary_min=100000,
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    poll_client = _build_fake_client(_malformed_result_line(job_id))
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: poll_client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_a, **_k: True
    )

    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "general_cv.md").write_text("# General CV\nQA experience.")
    import src.core.matcher as matcher_module

    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "src.core.batch_evaluation._submit_jsonl_batch",
        lambda *_args, **_kwargs: ("batches/retry-1", "JOB_STATE_PENDING"),
    )

    logs: list[tuple[str, str]] = []
    await poll_in_flight_batches(
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append((level, msg)),
    )

    job = database.get_job(job_id, db_path=str(tmp_db))
    assert job.status == "scraped"
    assert job.batchAttempts == 1

    round_logs = [msg for _level, msg in logs if "Evaluation round complete" in msg]
    assert len(round_logs) == 1
    assert "1 failed" in round_logs[0]

    retry_logs = [msg for _level, msg in logs if "Auto-retrying" in msg]
    assert len(retry_logs) == 1
    assert "1" in retry_logs[0]

    batches = database.list_batch_jobs(db_path=str(tmp_db))
    retry_batches = [b for b in batches if b["kind"] == "retry"]
    assert len(retry_batches) == 1
    assert retry_batches[0]["jobIds"] == [job_id]
    assert json.loads(retry_batches[0]["searchRemoteTypes"]) == ["remote"]
    assert retry_batches[0]["searchSeniorities"] == "mid"
    assert retry_batches[0]["searchEmploymentTypes"] == "Full-time"
    assert retry_batches[0]["searchSalaryMin"] == 100000


@pytest.mark.asyncio
async def test_cancel_path_does_not_auto_retry(tmp_db, tmp_path, monkeypatch):
    """Cancel clears the round without a summary, so poison jobs are not auto-retried."""
    job_id = _seed_scraped_job(tmp_db)
    database.increment_batch_attempts(job_id, db_path=str(tmp_db))

    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "general_cv.md").write_text("# General CV\nQA experience.")
    import src.core.matcher as matcher_module

    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))

    submit_calls = []

    async def fake_submit(*_args, **_kwargs):
        submit_calls.append(True)
        return []

    monkeypatch.setattr(
        "src.core.batch_poller.submit_batch_evaluation",
        fake_submit,
    )

    logs: list[str] = []
    # Empty in-flight after cancel: poller resets accumulator, no summary, no retry.
    await poll_in_flight_batches(
        db_path=str(tmp_db),
        log_func=lambda msg, level="info": logs.append(msg),
    )

    assert submit_calls == []
    assert not any("Auto-retrying" in msg for msg in logs)
    assert not any("Evaluation round complete" in msg for msg in logs)
    batches = database.list_batch_jobs(db_path=str(tmp_db))
    assert batches == []


@pytest.mark.asyncio
async def test_auto_retry_skips_zero_and_exhausted_attempts(
    tmp_db, tmp_path, monkeypatch
):
    """Auto-retry only covers Scraped jobs with 0 < batchAttempts < poison max."""
    failed_id = _seed_scraped_job(tmp_db, title="Failed QA", company="FailCo")
    never_id = _seed_scraped_job(tmp_db, title="Never QA", company="NeverCo")
    exhausted_id = _seed_scraped_job(tmp_db, title="Exhausted QA", company="MaxCo")
    for _ in range(POISON_MAX_ATTEMPTS):
        database.increment_batch_attempts(exhausted_id, db_path=str(tmp_db))

    batch_jobs.create_batch_job(
        batch_name="batches/search-mixed",
        display_name="search-mixed",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[failed_id],
        search_remote_types=["remote"],
        search_seniorities="any",
        submitted_at=datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        db_path=str(tmp_db),
    )

    poll_client = _build_fake_client(_malformed_result_line(failed_id))
    monkeypatch.setattr("src.core.batch_poller.get_client", lambda: poll_client)
    monkeypatch.setattr(
        "src.core.batch_poller.is_due_for_poll", lambda *_a, **_k: True
    )

    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "general_cv.md").write_text("# General CV\nQA experience.")
    import src.core.matcher as matcher_module

    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))
    monkeypatch.setattr("src.core.batch_evaluation.get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "src.core.batch_evaluation._submit_jsonl_batch",
        lambda *_args, **_kwargs: ("batches/retry-mixed", "JOB_STATE_PENDING"),
    )

    await poll_in_flight_batches(db_path=str(tmp_db))

    assert database.get_job(failed_id, db_path=str(tmp_db)).batchAttempts == 1
    assert database.get_job(never_id, db_path=str(tmp_db)).batchAttempts == 0
    assert (
        database.get_job(exhausted_id, db_path=str(tmp_db)).batchAttempts
        == POISON_MAX_ATTEMPTS
    )

    retry_batches = [
        b for b in database.list_batch_jobs(db_path=str(tmp_db)) if b["kind"] == "retry"
    ]
    assert len(retry_batches) == 1
    assert retry_batches[0]["jobIds"] == [failed_id]
