"""Tracer tests: Pre-Evaluation Filters own remote-type gating."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_normalize_remote_type_maps_in_office_variants():
    from src.core.pre_evaluation import normalize_remote_type

    assert normalize_remote_type("in office") == "in_office"
    assert normalize_remote_type("IN_OFFICE") == "in_office"
    assert normalize_remote_type("remote") == "remote"


def test_remote_type_filter_rejects_mismatch():
    from src.core.pre_evaluation import passes_remote_type_filter

    job = {"remoteType": "in office"}
    assert passes_remote_type_filter(job, ["remote"]) is False


def test_remote_type_filter_accepts_match():
    from src.core.pre_evaluation import passes_remote_type_filter

    job = {"remoteType": "remote"}
    assert passes_remote_type_filter(job, ["remote"]) is True


def test_remote_type_filter_any_skips_gating():
    from src.core.pre_evaluation import passes_remote_type_filter

    job = {"remoteType": "in_office"}
    assert passes_remote_type_filter(job, ["any"]) is True
    assert passes_remote_type_filter(job, None) is True
    assert passes_remote_type_filter(job, []) is True
