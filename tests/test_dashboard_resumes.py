import os
import sys
import pytest

# Add root directory to path to import prototype_dashboard
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from prototype_dashboard import app
import prototype_dashboard

client = TestClient(app)

def test_get_resumes_returns_list_of_markdown_resumes(tmp_path, monkeypatch):
    # Create a temporary resumes directory
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    
    # Create mock resumes
    qa_file = resumes_dir / "qa.md"
    qa_file.write_text("# QA Resume\nContent here")
    
    pm_file = resumes_dir / "project_manager.md"
    pm_file.write_text("# PM Resume\nContent there")
    
    # Create a non-markdown file to ensure it's ignored
    other_file = resumes_dir / "notes.txt"
    other_file.write_text("should be ignored")
    
    # Patch the resumes directory path in prototype_dashboard
    monkeypatch.setattr(prototype_dashboard, "RESUMES_DIR", str(resumes_dir))
    
    response = client.get("/api/resumes")
    assert response.status_code == 200
    
    data = response.json()
    # Expecting a list of objects containing name and content
    assert len(data) == 2
    
    names = [r["name"] for r in data]
    assert "qa.md" in names
    assert "project_manager.md" in names
    assert "notes.txt" not in names
    
    # Check that contents are read correctly
    qa_item = next(r for r in data if r["name"] == "qa.md")
    assert qa_item["content"] == "# QA Resume\nContent here"

def test_get_resumes_returns_empty_when_directory_does_not_exist(monkeypatch):
    monkeypatch.setattr(prototype_dashboard, "RESUMES_DIR", "/nonexistent_directory_for_resumes")
    response = client.get("/api/resumes")
    assert response.status_code == 200
    assert response.json() == []
