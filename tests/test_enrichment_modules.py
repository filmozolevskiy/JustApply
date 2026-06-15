"""Tracer tests: Enrichment package exposes behavior through focused submodules."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_connection_note_module_generates_fallback_within_limit():
    from src.core.enrichment.connection_note import minimal_fallback_template

    assert len(minimal_fallback_template("recruiter")) <= 200


@pytest.mark.asyncio
async def test_source_module_delegates_to_contact_sample_on_cache_miss(monkeypatch):
    from unittest.mock import AsyncMock

    from src.core.enrichment import source as source_module

    job = {"title": "QA", "company": "Acme", "contacts": []}
    mock_apify = AsyncMock(return_value=[])
    mock_classify = AsyncMock(return_value=[])

    monkeypatch.setattr(source_module, "_run_apify_actor", mock_apify)
    monkeypatch.setattr(source_module, "classify_contacts", mock_classify)

    await source_module.source_contacts(job)

    mock_apify.assert_called_once()
