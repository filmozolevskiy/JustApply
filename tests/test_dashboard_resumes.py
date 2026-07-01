import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.web.server as server_module
from fastapi.testclient import TestClient
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


def test_delete_resume_removes_file(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    qa_file = resumes_dir / "qa.md"
    qa_file.write_text("# QA")
    pm_file = resumes_dir / "project_manager.md"
    pm_file.write_text("# PM")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.delete(
        "/api/resumes/project_manager.md",
        params={"active_resume": "qa.md"},
    )
    assert response.status_code == 200
    assert not pm_file.exists()
    assert qa_file.exists()

    list_response = client.get("/api/resumes")
    names = [r["name"] for r in list_response.json()]
    assert "project_manager.md" not in names
    assert "qa.md" in names


def test_delete_active_resume_rejected(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    qa_file = resumes_dir / "qa.md"
    qa_file.write_text("# QA")
    pm_file = resumes_dir / "project_manager.md"
    pm_file.write_text("# PM")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.delete(
        "/api/resumes/qa.md",
        params={"active_resume": "qa.md"},
    )
    assert response.status_code == 409
    assert "Active Resume Profile" in response.json()["detail"]
    assert qa_file.exists()
    assert pm_file.exists()


def test_delete_last_remaining_resume_rejected(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    only_file = resumes_dir / "qa.md"
    only_file.write_text("# QA")

    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.delete(
        "/api/resumes/qa.md",
        params={"active_resume": "other.md"},
    )
    assert response.status_code == 409
    assert "last remaining" in response.json()["detail"].lower()
    assert only_file.exists()


def test_convert_resume_pdf_returns_markdown_without_writing(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    converted = "# QA Engineer Profile\n\n**SUMMARY**\nConverted from PDF."
    pdf_bytes = b"%PDF-1.4 fake resume bytes"

    with patch.object(server_module, "get_api_key", return_value="test-key"), patch.object(
        server_module,
        "generate_text_from_pdf",
        new=AsyncMock(return_value=converted),
    ) as mock_convert:
        response = client.post(
            "/api/resumes/convert",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["content"] == converted
    assert list(resumes_dir.iterdir()) == []
    mock_convert.assert_awaited_once()
    assert mock_convert.await_args.args[0] == pdf_bytes


def test_convert_resume_pdf_rejects_missing_api_key(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    with patch.object(server_module, "get_api_key", return_value=None):
        response = client.post(
            "/api/resumes/convert",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
    assert list(resumes_dir.iterdir()) == []


def test_convert_resume_pdf_rejects_llm_failure(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    with patch.object(server_module, "get_api_key", return_value="test-key"), patch.object(
        server_module,
        "generate_text_from_pdf",
        new=AsyncMock(side_effect=RuntimeError("Gemini API error")),
    ):
        response = client.post(
            "/api/resumes/convert",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert response.status_code == 503
    assert "Gemini API error" in response.json()["detail"]
    assert list(resumes_dir.iterdir()) == []


def test_convert_resume_pdf_rejects_non_pdf(tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    monkeypatch.setattr(server_module, "RESUMES_DIR", str(resumes_dir))

    response = client.post(
        "/api/resumes/convert",
        files={"file": ("resume.docx", b"not a pdf", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert list(resumes_dir.iterdir()) == []
