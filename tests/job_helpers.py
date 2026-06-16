"""Shared Job fixtures for tests."""

from src.schemas import Contact, Job


def make_job(**overrides) -> Job:
    data = {
        "id": 1,
        "title": "QA Engineer",
        "company": "Acme",
        "status": "sourced",
        "contacts": [],
        "shouldProceed": False,
    }
    data.update(overrides)
    if "contacts" in overrides and overrides["contacts"] and isinstance(overrides["contacts"][0], dict):
        data["contacts"] = [Contact(**c) for c in overrides["contacts"]]
    return Job(**data)
