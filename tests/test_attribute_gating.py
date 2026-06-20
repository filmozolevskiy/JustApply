"""Tracer tests: post-evaluation attribute merge and gating."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_merge_uses_llm_attributes_when_present():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {"remoteType": "in_office", "seniority": "junior"}
    evaluation = {"remoteType": "hybrid", "seniority": "senior"}

    merged = merge_job_attributes(scraper, evaluation)

    assert merged["remoteType"] == "hybrid"
    assert merged["seniority"] == "senior"


def test_merge_falls_back_per_field_to_scraper():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {"remoteType": "remote", "seniority": "mid"}
    evaluation = {"remoteType": "hybrid"}

    merged = merge_job_attributes(scraper, evaluation)

    assert merged["remoteType"] == "hybrid"
    assert merged["seniority"] == "mid"


def test_merge_uses_scraper_when_evaluation_empty():
    from src.core.attribute_gating import merge_job_attributes

    scraper = {"remoteType": "remote", "seniority": "senior"}
    merged = merge_job_attributes(scraper, {})

    assert merged["remoteType"] == "remote"
    assert merged["seniority"] == "senior"


def test_attribute_gate_rejects_remote_type_mismatch():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("in_office", "senior", ["remote"], "any") is False
    assert passes_attribute_gate("remote", "senior", ["remote"], "any") is True


def test_attribute_gate_rejects_seniority_mismatch():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("remote", "junior", ["any"], "senior") is False
    assert passes_attribute_gate("remote", "senior", ["any"], "senior") is True


def test_attribute_gate_any_skips_checks():
    from src.core.attribute_gating import passes_attribute_gate

    assert passes_attribute_gate("in_office", "junior", ["any"], "any") is True


def test_format_attribute_mismatch_includes_job_and_reason():
    from src.core.attribute_gating import format_attribute_mismatch

    msg = format_attribute_mismatch(
        "QA Lead",
        "Acme",
        remote_type="in_office",
        seniority="senior",
        allowed_remote_types=["remote"],
        seniorities="senior",
    )

    assert "Attribute mismatch" in msg
    assert "QA Lead" in msg
    assert "Acme" in msg
    assert "in_office" in msg


def test_unclassified_only_on_full_matcher_failure():
    from src.core.attribute_gating import is_unclassified

    assert is_unclassified({}) is True
    assert is_unclassified({"remoteType": "remote"}) is False
    assert is_unclassified({"seniority": "mid"}) is False
