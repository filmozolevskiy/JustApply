"""Tracer tests: Enrichment package exposes behavior through focused submodules."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_source_module_delegates_to_contact_sample_on_cache_miss(monkeypatch):
    from unittest.mock import AsyncMock

    from src.core.enrichment import source as source_module
    import src.db.cache as cache_mod
    from src.schemas import OutreachSettings

    job = {"title": "QA", "company": "Acme", "companyUrl": "https://www.linkedin.com/company/acme/", "contacts": []}
    mock_apify = AsyncMock(return_value=[])
    mock_classify = AsyncMock(return_value=[])

    monkeypatch.setattr(source_module, "_run_apify_actor", mock_apify)
    monkeypatch.setattr(source_module, "classify_contacts", mock_classify)
    # Isolate from real DB: force cache miss regardless of data/job_tracker.db state
    monkeypatch.setattr(cache_mod, "get_contact_sample", lambda *a, **kw: None)
    monkeypatch.setattr(cache_mod, "set_contact_sample", lambda *a, **kw: None)

    await source_module.source_contacts(
        job, settings=OutreachSettings(target_recruiters=False, target_russian_speakers=False)
    )

    mock_apify.assert_called_once()
