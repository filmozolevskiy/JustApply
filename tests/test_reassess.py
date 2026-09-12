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
async def test_reassess_persists_annual_band_from_posted_salary(tmp_db):
    """Single-job reassess writes Annual Posted Salary when matcher returns pay facts."""
    job_id = _seed_job(tmp_db, location="Berlin, Germany", salary="")
    evaluation = _matcher_evaluation(
        salary="$125,000 - $145,000",
        postedSalary={
            "period": "yearly",
            "amountMin": 125000,
            "amountMax": 145000,
            "currency": "USD",
        },
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id)

    assert updated.salary == "$125,000 - $145,000"
    assert updated.annualMin == 125000
    assert updated.annualMax == 145000
    assert updated.annualCurrency == "USD"
    assert updated.status == "matched"


@pytest.mark.asyncio
async def test_reassess_salary_min_rejects_when_annual_max_below(tmp_db):
    """Salary Min gate demotes Matched when annualMax is below Min (ADR 0014)."""
    job_id = _seed_job(tmp_db, status="matched")
    evaluation = _matcher_evaluation(
        salary="$100,000 - $110,000",
        postedSalary={
            "period": "yearly",
            "amountMin": 100000,
            "amountMax": 110000,
            "currency": "USD",
        },
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, salary_min=120000)

    assert updated.annualMax == 110000
    assert updated.status == "rejected"
    assert updated.matchScore == 82


@pytest.mark.asyncio
async def test_reassess_salary_min_passes_when_annual_max_reaches(tmp_db):
    """Band top at/above Salary Min keeps Matched after reassess."""
    job_id = _seed_job(tmp_db, status="matched")
    evaluation = _matcher_evaluation(
        salary="$100,000 - $130,000",
        postedSalary={
            "period": "yearly",
            "amountMin": 100000,
            "amountMax": 130000,
            "currency": "USD",
        },
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, salary_min=120000)

    assert updated.annualMax == 130000
    assert updated.status == "matched"


@pytest.mark.asyncio
async def test_reassess_salary_min_unknown_pay_stays_matched(tmp_db):
    """Missing Posted Salary still passes Salary Min gate (unknown-pay pass)."""
    job_id = _seed_job(tmp_db, status="matched")
    evaluation = _matcher_evaluation(salary="")
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, salary_min=120000)

    assert updated.annualMax is None
    assert updated.status == "matched"


@pytest.mark.asyncio
async def test_reassess_salary_min_keeps_accepted_lane(tmp_db):
    """Accepted+ keep lane on Salary Min fail; annual fields still update."""
    job_id = _seed_job(tmp_db, status="accepted")
    evaluation = _matcher_evaluation(
        salary="$100,000 - $110,000",
        postedSalary={
            "period": "yearly",
            "amountMin": 100000,
            "amountMax": 110000,
            "currency": "USD",
        },
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, salary_min=120000)

    assert updated.annualMax == 110000
    assert updated.status == "accepted"


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
async def test_reassess_job_service_parses_salary_min_for_gate(tmp_db):
    """Service parses Job Search Settings Salary Min and applies it on reassess."""
    job_id = _seed_job(tmp_db, status="matched")
    evaluation = _matcher_evaluation(
        salary="$100,000 - $110,000",
        postedSalary={
            "period": "yearly",
            "amountMin": 100000,
            "amountMax": 110000,
            "currency": "USD",
        },
    )
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await reassess_job(job_id, salary="$120k")

    assert updated.annualMax == 110000
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


@pytest.mark.asyncio
async def test_reassess_all_applies_annualizer_and_salary_gate(tmp_db):
    """Reassess-all uses the same annualizer + Salary Min path as single reassess."""
    keep_id = _seed_job(tmp_db, title="Keep Role", company="Alpha")
    reject_id = _seed_job(tmp_db, title="Reject Role", company="Beta")

    async def fake_evaluate(job_dict, *_args, **_kwargs):
        title = job_dict.get("title") or ""
        if title == "Reject Role":
            return _matcher_evaluation(
                salary="$100,000 - $110,000",
                postedSalary={
                    "period": "yearly",
                    "amountMin": 100000,
                    "amountMax": 110000,
                    "currency": "USD",
                },
            )
        return _matcher_evaluation(
            salary="$100,000 - $130,000",
            postedSalary={
                "period": "yearly",
                "amountMin": 100000,
                "amountMax": 130000,
                "currency": "USD",
            },
        )

    with patch("src.pipelines.evaluate_job", new=AsyncMock(side_effect=fake_evaluate)):
        updated = await reassess_all_jobs(
            salary="$120k",
            log_func=lambda m, level="info": None,
        )

    by_id = {j.id: j for j in updated}
    assert by_id[keep_id].status == "matched"
    assert by_id[keep_id].annualMax == 130000
    assert by_id[reject_id].status == "rejected"
    assert by_id[reject_id].annualMax == 110000


@pytest.mark.asyncio
async def test_reassess_role_relevant_false_rejects_matched_job(tmp_db):
    """Current search query + roleRelevant false demotes Matched as Role-filtered."""
    job_id = _seed_job(tmp_db, status="matched", title="Software Engineer")
    evaluation = _matcher_evaluation(roleRelevant=False)
    mock_eval = AsyncMock(return_value=evaluation)
    with patch("src.pipelines.evaluate_job", new=mock_eval):
        updated = await run_reassess_pipeline(job_id, search_query="QA")

    assert mock_eval.await_args.kwargs["search_query"] == "QA"
    assert updated.status == "rejected"
    assert updated.roleFiltered is True
    assert updated.roleFilteredReason == "Searched QA vs Software Engineer"
    assert updated.matchScore == 82
    activity = [entry.message for entry in updated.activityLog]
    assert not any("Role Relevance" in message for message in activity)


@pytest.mark.asyncio
async def test_reassess_role_relevant_false_rejects_scraped_job(tmp_db):
    """Scraped + roleRelevant false → Rejected Role-filtered Job."""
    job_id = _seed_job(tmp_db, status="scraped", title="Software Engineer")
    evaluation = _matcher_evaluation(roleRelevant=False)
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, search_query="QA")

    assert updated.status == "rejected"
    assert updated.roleFiltered is True
    assert updated.roleFilteredReason == "Searched QA vs Software Engineer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lane",
    ["accepted", "applied", "interviewing"],
)
async def test_reassess_role_relevant_false_keeps_downstream_lane(tmp_db, lane):
    """Accepted+ keep lane on Role Relevance fail; flag is not persisted."""
    job_id = _seed_job(tmp_db, status=lane, title="Software Engineer")
    evaluation = _matcher_evaluation(roleRelevant=False)
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, search_query="QA")

    assert updated.status == lane
    assert updated.roleFiltered is False
    assert updated.roleFilteredReason == ""
    assert updated.matchScore == 82


@pytest.mark.asyncio
@pytest.mark.parametrize("role_relevant", [True, None, "omitted"])
async def test_reassess_unsure_role_relevant_does_not_demote(tmp_db, role_relevant):
    """true / null / omitted roleRelevant does not demote for Role Relevance."""
    job_id = _seed_job(tmp_db, status="matched", title="Software Engineer")
    evaluation = _matcher_evaluation()
    if role_relevant != "omitted":
        evaluation["roleRelevant"] = role_relevant
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, search_query="QA")

    assert updated.status == "matched"
    assert updated.roleFiltered is False


@pytest.mark.asyncio
async def test_reassess_blank_query_skips_role_relevance(tmp_db):
    """Blank current query skips Role Relevance even when JSON says false."""
    job_id = _seed_job(tmp_db, status="matched", title="Software Engineer")
    evaluation = _matcher_evaluation(roleRelevant=False)
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, search_query="  ")

    assert updated.status == "matched"
    assert updated.roleFiltered is False


@pytest.mark.asyncio
async def test_reassess_passing_role_clears_role_filtered_flag(tmp_db):
    """A later reassess that passes Role Relevance clears the Role-filtered flag."""
    job_id = _seed_job(
        tmp_db,
        status="rejected",
        title="Software Engineer",
        roleFiltered=True,
        roleFilteredReason="Searched QA vs Software Engineer",
    )
    evaluation = _matcher_evaluation(roleRelevant=True)
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await run_reassess_pipeline(job_id, search_query="Software Engineer")

    assert updated.status == "rejected"
    assert updated.roleFiltered is False
    assert updated.roleFilteredReason == ""


@pytest.mark.asyncio
async def test_reassess_job_service_forwards_search_query(tmp_db):
    """Dashboard path: service forwards current Job Search Settings query."""
    job_id = _seed_job(tmp_db, status="matched", title="Software Engineer")
    evaluation = _matcher_evaluation(roleRelevant=False)
    with patch(
        "src.pipelines.evaluate_job",
        new=AsyncMock(return_value=evaluation),
    ):
        updated = await reassess_job(job_id, search_query="QA")

    assert updated.status == "rejected"
    assert updated.roleFiltered is True
    assert updated.roleFilteredReason == "Searched QA vs Software Engineer"


@pytest.mark.asyncio
async def test_reassess_all_uses_current_search_query(tmp_db):
    """Reassess-all applies Role Relevance with the same current query."""
    keep_id = _seed_job(tmp_db, title="QA Engineer", company="Alpha")
    reject_id = _seed_job(tmp_db, title="Software Engineer", company="Beta")

    async def fake_evaluate(job_dict, *_args, **kwargs):
        assert kwargs.get("search_query") == "QA"
        title = job_dict.get("title") or ""
        if title == "Software Engineer":
            return _matcher_evaluation(roleRelevant=False)
        return _matcher_evaluation(roleRelevant=True)

    with patch("src.pipelines.evaluate_job", new=AsyncMock(side_effect=fake_evaluate)):
        updated = await reassess_all_jobs(
            search_query="QA",
            log_func=lambda m, level="info": None,
        )

    by_id = {j.id: j for j in updated}
    assert by_id[keep_id].status == "matched"
    assert by_id[keep_id].roleFiltered is False
    assert by_id[reject_id].status == "rejected"
    assert by_id[reject_id].roleFiltered is True
