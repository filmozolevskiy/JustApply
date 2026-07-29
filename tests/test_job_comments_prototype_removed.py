"""Job Comments UI prototype must be gone after production Comment Thread landed."""
import os

from fastapi.testclient import TestClient
from src.web.server import app

client = TestClient(app)

_WEB_ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "web")


def test_job_comments_prototype_route_returns_404():
    resp = client.get("/prototype/job-comments")
    assert resp.status_code == 404


def test_job_comments_prototype_assets_removed():
    paths = [
        os.path.join(_WEB_ROOT, "prototype", "job-comments.html"),
        os.path.join(_WEB_ROOT, "static", "css", "prototype-job-comments.css"),
        os.path.join(_WEB_ROOT, "static", "js", "prototype", "jobCommentsUiPrototype.js"),
    ]
    for path in paths:
        assert not os.path.exists(path), f"Prototype artifact must be deleted: {path}"


def test_server_has_no_job_comments_prototype_route():
    path = os.path.join(_WEB_ROOT, "server.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "/prototype/job-comments" not in content
    assert "PROTOTYPE_JOB_COMMENTS" not in content


def test_prototype_notes_job_comments_verdict_retained():
    notes = os.path.join(_WEB_ROOT, "prototype", "NOTES.md")
    assert os.path.exists(notes)
    with open(notes, encoding="utf-8") as f:
        content = f.read()
    assert "Verdict — job comments" in content
    assert "Mix: B card + C drawer" in content
    assert "Production" in content.split("# Job Comments")[1].split("# Favorite")[0]
    assert "Runnable `/prototype/job-comments`" in content.split("# Job Comments")[1].split("# Favorite")[0]
    assert "removed" in content.split("# Job Comments")[1].split("# Favorite")[0].lower()
