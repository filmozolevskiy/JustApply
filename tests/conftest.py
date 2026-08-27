"""Shared pytest fixtures for JustApply tests."""

import pytest
from src.core.enrichment.classifier import normalize_apify_employee


@pytest.fixture
def apify_employee_item() -> dict:
    """Real-world-shaped Apify LinkedIn employee profile.

    ``currentPosition`` and ``location`` are Apify extension fields that
    enrichment copies via ``normalize_apify_employee`` but does not declare on
    ``Contact``. ``extra="allow"`` keeps them on persisted job rows.
    """
    return {
        "firstName": "Ivan",
        "lastName": "Petrov",
        "headline": "Backend Developer",
        "linkedinUrl": "https://www.linkedin.com/in/ivan-petrov/",
        "currentPosition": "Senior Engineer at TechCorp",
        "location": "Montreal, QC",
        "languages": [{"name": "Russian"}, {"name": "English"}],
    }


@pytest.fixture
def apify_normalized_contact(apify_employee_item) -> dict:
    """Contact-like dict produced by enrichment classification."""
    return normalize_apify_employee(apify_employee_item)
