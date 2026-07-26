from unittest.mock import AsyncMock, patch

import pytest
from src import db as database
from src.pipelines import run_reassess_pipeline
from src.service.just_apply import reassess_all_jobs, reassess_job


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "general_cv.md").write_text("# General CV\nDelivery and QA")
    import src.core.matcher as matcher_module
    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))
    return db_path


def _seed_job(db_path, **overrides):
    job = {
        "title": "QA Engineer",
        "company": "Acme",
        "description": "Need Python and Playwright.",
        "matchScore": 40,
        "matchType": "no-match",
        "shouldProceed": False,
        "resumeUsed": "old.md",
        "strengths": ["Old strength"],
        "gaps": ["Old gap"],
        "remoteType": "remote",
        "seniority": "mid",
        "employmentType": "Contract",
        "status": "matched",
    }
    job.update(overrides)
    job_id = database.add_job(job, db_path=str(db_path))
    return job_id


def _matcher_evaluation(**overrides):
    evaluation = {
        "matchScore": 82,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Playwright automation"],
        "gaps": ["No Kubernetes"],
        "remoteType": "hybrid",
        "seniority": "senior",
        "employmentType": "Full-time",
        "summary": "Updated job summary.",
        "isRecruiter": False,
        "salary": "$100k",
    }
    evaluation.update(overrides)
    return evaluation


@pytest.mark.asyncio
async def test_reassess_updates_job_scores(tmp_db):
    job_id = _seed_job(tmp_db)
    evaluation = _matcher_evaluation()
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id)

    assert updated.matchScore == 82
    assert updated.matchType == "match"
    assert updated.shouldProceed is True
    assert updated.resumeUsed == "general_cv.md"
    assert updated.strengths == ["Playwright automation"]
    assert updated.remoteType == "hybrid"
    assert updated.seniority == "senior"
    assert updated.employmentType == "Full-time"
    assert updated.description == "Updated job summary."
    assert any("Re-assessed" in entry.message for entry in updated.activityLog)


@pytest.mark.asyncio
async def test_reassess_gate_failure_rejects_matched_job(tmp_db):
    """Matched + Employment Type gate fail → Rejected; fields still update."""
    job_id = _seed_job(tmp_db, status="matched", employmentType="Full-time")
    evaluation = _matcher_evaluation(employmentType="Contract")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(
            job_id,
            employment_types="Full-time",
        )

    assert updated.employmentType == "Contract"
    assert updated.status == "rejected"
    assert updated.matchScore == 82


@pytest.mark.asyncio
async def test_reassess_gate_failure_rejects_scraped_job(tmp_db):
    """Scraped + Employment Type gate fail → Rejected."""
    job_id = _seed_job(tmp_db, status="scraped", employmentType="Full-time")
    evaluation = _matcher_evaluation(employmentType="Part-time")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(
            job_id,
            employment_types="Full-time",
        )

    assert updated.employmentType == "Part-time"
    assert updated.status == "rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lane",
    ["accepted", "applied", "interviewing", "rejected"],
)
async def test_reassess_gate_failure_keeps_downstream_lane(tmp_db, lane):
    """Accepted+ keep lane on gate fail; Employment Type still updates."""
    job_id = _seed_job(tmp_db, status=lane, employmentType="Full-time")
    evaluation = _matcher_evaluation(employmentType="Contract")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(
            job_id,
            employment_types="Full-time",
        )

    assert updated.employmentType == "Contract"
    assert updated.status == lane
    assert updated.matchScore == 82


@pytest.mark.asyncio
async def test_reassess_any_employment_type_skips_gate(tmp_db):
    """CLI/default “any” does not Reject solely for Employment Type."""
    job_id = _seed_job(tmp_db, status="matched", employmentType="Full-time")
    evaluation = _matcher_evaluation(employmentType="Contract")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id)

    assert updated.employmentType == "Contract"
    assert updated.status == "matched"


@pytest.mark.asyncio
async def test_reassess_job_service_forwards_search_settings_gate(tmp_db):
    """Dashboard path: service forwards Job Search Settings into the gate."""
    job_id = _seed_job(tmp_db, status="matched", employmentType="Full-time")
    evaluation = _matcher_evaluation(employmentType="Temporary")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await reassess_job(
            job_id,
            employment_types="Full-time,Contract",
            allowed_remote_types=["hybrid"],
            seniorities="senior",
        )

    assert updated.employmentType == "Temporary"
    assert updated.status == "rejected"


@pytest.mark.asyncio
async def test_reassess_raises_when_job_missing(tmp_db):
    with pytest.raises(ValueError, match="Job not found"):
        await run_reassess_pipeline(9999)


@pytest.mark.asyncio
async def test_reassess_all_jobs(tmp_db):
    id1 = _seed_job(tmp_db, title="Role A")
    id2 = _seed_job(tmp_db, title="Role B", company="Beta")
    evaluation = _matcher_evaluation(
        matchScore=75,
        strengths=["Match"],
        gaps=[],
        remoteType="remote",
        seniority="mid",
        summary="Summary.",
        salary="",
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await reassess_all_jobs(log_func=lambda m, level="info": None)

    by_id = {j.id: j for j in updated}
    assert by_id[id1].matchScore == 75
    assert by_id[id2].matchScore == 75
