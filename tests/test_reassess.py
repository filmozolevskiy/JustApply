import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

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
    }
    job.update(overrides)
    job_id = database.add_job(job, db_path=str(db_path))
    return job_id


@pytest.mark.asyncio
async def test_reassess_updates_job_scores(tmp_db):
    job_id = _seed_job(tmp_db)
    evaluation = {
        "matchScore": 82,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Playwright automation"],
        "gaps": ["No Kubernetes"],
        "remoteType": "hybrid",
        "seniority": "senior",
        "summary": "Updated job summary.",
        "isRecruiter": False,
        "salary": "$100k",
    }
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
    assert updated.description == "Updated job summary."
    assert any("Re-assessed" in entry.message for entry in updated.activityLog)


@pytest.mark.asyncio
async def test_reassess_raises_when_job_missing(tmp_db):
    with pytest.raises(ValueError, match="Job not found"):
        await run_reassess_pipeline(9999)


@pytest.mark.asyncio
async def test_reassess_all_jobs(tmp_db):
    id1 = _seed_job(tmp_db, title="Role A")
    id2 = _seed_job(tmp_db, title="Role B", company="Beta")
    evaluation = {
        "matchScore": 75,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Match"],
        "gaps": [],
        "remoteType": "remote",
        "seniority": "mid",
        "summary": "Summary.",
        "isRecruiter": False,
        "salary": "",
    }
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await reassess_all_jobs(log_func=lambda m, l="info": None)

    by_id = {j.id: j for j in updated}
    assert by_id[id1].matchScore == 75
    assert by_id[id2].matchScore == 75
