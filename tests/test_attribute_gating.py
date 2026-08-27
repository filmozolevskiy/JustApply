"""Tracer tests: post-evaluation attribute merge and gating."""


def test_merge_uses_llm_attributes_when_present():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {
        "remoteType": "in_office",
        "seniority": "junior",
        "employmentType": "Contract",
    }
    evaluation = {
        "remoteType": "hybrid",
        "seniority": "senior",
        "employmentType": "Full-time",
    }

    merged = merge_job_attributes(scraper, evaluation)

    assert merged["remoteType"] == "hybrid"
    assert merged["seniority"] == "senior"
    assert merged["employmentType"] == "Full-time"

def test_merge_falls_back_per_field_to_scraper():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {
        "remoteType": "remote",
        "seniority": "mid",
        "employmentType": "Contract",
    }
    evaluation = {"remoteType": "hybrid"}

    merged = merge_job_attributes(scraper, evaluation)

    assert merged["remoteType"] == "hybrid"
    assert merged["seniority"] == "mid"
    assert merged["employmentType"] == "Contract"

def test_merge_uses_scraper_when_evaluation_empty():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {
        "remoteType": "remote",
        "seniority": "senior",
        "employmentType": "Part-time",
    }
    merged = merge_job_attributes(scraper, {})

    assert merged["remoteType"] == "remote"
    assert merged["seniority"] == "senior"
    assert merged["employmentType"] == "Part-time"

def test_attribute_gate_rejects_remote_type_mismatch():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("in_office", "senior", ["remote"], "any") is False
    assert passes_attribute_gate("remote", "senior", ["remote"], "any") is True

def test_attribute_gate_rejects_seniority_mismatch():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("remote", "junior", ["any"], "senior") is False
    assert passes_attribute_gate("remote", "senior", ["any"], "senior") is True

def test_attribute_gate_rejects_employment_type_mismatch():
    from src.core.attribute_gating import passes_attribute_gate

    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            employment_type="Contract",
            employment_types="Full-time",
        )
        is False
    )
    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            employment_type="Full-time",
            employment_types="Full-time",
        )
        is True
    )

def test_attribute_gate_any_skips_checks():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("in_office", "junior", ["any"], "any") is True
    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            employment_type="Contract",
            employment_types="any",
        )
        is True
    )

def test_format_attribute_mismatch_includes_job_and_reason():
    from src.core.attribute_gating import format_attribute_mismatch

    msg = format_attribute_mismatch(
        "QA Lead",
        "Acme",
        remote_type="in_office",
        seniority="senior",
        allowed_remote_types=["remote"],
        seniorities="senior",
        employment_type="Contract",
        employment_types="Full-time",
    )

    assert "Attribute mismatch" in msg
    assert "QA Lead" in msg
    assert "Acme" in msg
    assert "in_office" in msg
    assert "Contract" in msg

def test_unclassified_only_on_full_matcher_failure():
    from src.core.attribute_gating import is_unclassified

    assert is_unclassified({}) is True
    assert is_unclassified({"remoteType": "remote"}) is False
    assert is_unclassified({"seniority": "mid"}) is False


def test_attribute_gate_rejects_when_annual_max_below_salary_min():
    from src.core.attribute_gating import passes_attribute_gate

    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=110000,
            salary_min=120000,
        )
        is False
    )


def test_attribute_gate_passes_when_annual_max_reaches_salary_min():
    from src.core.attribute_gating import passes_attribute_gate

    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=130000,
            salary_min=120000,
        )
        is True
    )
    # Band 100k–130k vs Min 120k: gate on annualMax (ADR 0014).
    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=130000,
            annual_min=100000,
            salary_min=120000,
        )
        is True
    )


def test_attribute_gate_unknown_pay_passes_when_salary_min_set():
    from src.core.attribute_gating import passes_attribute_gate

    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=None,
            salary_min=120000,
        )
        is True
    )


def test_attribute_gate_disabled_salary_min_skips_check():
    from src.core.attribute_gating import passes_attribute_gate

    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=50000,
            salary_min=None,
        )
        is True
    )


def test_attribute_gate_salary_compare_is_currency_agnostic():
    from src.core.attribute_gating import passes_attribute_gate

    # CAD 120000 and USD floor 120000 compare as bare numbers.
    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=120000,
            salary_min=120000,
        )
        is True
    )
    assert (
        passes_attribute_gate(
            "remote",
            "senior",
            ["any"],
            "any",
            annual_max=119999,
            salary_min=120000,
        )
        is False
    )


def test_format_attribute_mismatch_includes_salary_reason():
    from src.core.attribute_gating import format_attribute_mismatch

    msg = format_attribute_mismatch(
        "QA Lead",
        "Acme",
        remote_type="remote",
        seniority="senior",
        allowed_remote_types=["any"],
        seniorities="any",
        annual_max=100000,
        salary_min=120000,
    )

    assert "Attribute mismatch" in msg
    assert "QA Lead" in msg
    assert "salary" in msg.lower()
    assert "100000" in msg
    assert "120000" in msg
