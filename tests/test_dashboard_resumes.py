import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
import src.web.server as server_module
from src.web.server import app

client = TestClient(app)


def test_get_resumes_returns_list_of_markdown_resumes(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()

    qa_file = resumes_dir / "qa.md"
    qa_file.write_text("# QA Resume\nContent here")

    pm_file = resumes_dir / "project_manager.md"
    pm_file.write_text("# PM Resume\nContent there")

    other_file = resumes_dir / "notes.txt"
    other_file.write_text("should be ignored")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.get("/api/resumes")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2

    names = [r["name"] for r in data]
    assert "qa.md" in names
    assert "project_manager.md" in names
    assert "notes.txt" not in names

    qa_item = next(r for r in data if r["name"] == "qa.md")
    assert qa_item["content"] == "# QA Resume\nContent here"


def test_get_resumes_returns_empty_when_directory_does_not_exist(monkeypatch):
    monkeypatch.setattr(server_module, "RESUMES_DIR", "/nonexistent_directory_for_resumes")
    response = client.get("/api/resumes")
    assert response.status_code == 200
    assert response.json() == []


def test_save_resume_updates_existing_verbatim(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    qa_file = resumes_dir / "qa.md"
    qa_file.write_text("# Old content")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    new_content = "# Updated\nExact verbatim text with **markdown**"
    response = client.post(
        "/api/resumes",
        json={"filename": "qa.md", "content": new_content},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "qa.md"
    assert data["content"] == new_content
    assert qa_file.read_text() == new_content


def test_save_resume_creates_new_with_sanitized_name(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    content = "any markdown works"
    response = client.post(
        "/api/resumes",
        json={"name": "Senior QA Engineer", "content": content},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "senior_qa_engineer.md"
    assert data["content"] == content
    created = resumes_dir / "senior_qa_engineer.md"
    assert created.exists()
    assert created.read_text() == content


def test_save_resume_collision_appends_timestamp_suffix(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    existing = resumes_dir / "qa.md"
    existing.write_text("original")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.post(
        "/api/resumes",
        json={"name": "QA", "content": "new copy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"].startswith("qa_")
    assert data["name"].endswith(".md")
    assert data["name"] != "qa.md"
    assert existing.read_text() == "original"
    assert (resumes_dir / data["name"]).read_text() == "new copy"
