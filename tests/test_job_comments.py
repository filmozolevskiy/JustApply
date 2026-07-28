"""Job Comments — post root end-to-end (PRD #185 / issue #186)."""

import json
import sqlite3

import pytest
import src.db.connection as _db_connection
from fastapi.testclient import TestClient
from src import db as database
from src.db import add_job, get_job, get_jobs, init_db
from src.db.connection import get_db_connection
from src.db.migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from src.web.server import app

from kanban_js import read_drawer_controller


def _fresh_db(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    return db_str


# ---------------------------------------------------------------------------
# Slice 1: Job model exposes comments list
# ---------------------------------------------------------------------------


def test_new_job_defaults_to_empty_comments(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)
    job = get_job(job_id, db_str)
    assert job.comments == []


def test_seed_jobs_expose_comments_list_not_string_blob(tmp_path):
    from src.schemas import Job

    db_str = _fresh_db(tmp_path)
    jobs = get_jobs(db_str, archived_filter="all")
    assert jobs
    job1 = next(j for j in jobs if j.id == 1)
    assert isinstance(job1.comments, list)
    assert "comments" in Job.model_fields
    assert "comment" not in Job.model_fields


# ---------------------------------------------------------------------------
# Slice 2: Legacy notes blob → one root Job Comment
# ---------------------------------------------------------------------------


def test_legacy_comment_blob_migrates_to_one_root_on_upgrade(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'matched',
            matchType TEXT DEFAULT 'match',
            comment TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs (title, company, status, matchType, comment) "
        "VALUES ('QA', 'Acme', 'matched', 'match', 'Legacy notes blob')"
    )
    conn.commit()
    conn.close()

    init_db(db_path)
    job = get_jobs(db_path)[0]
    assert len(job.comments) == 1
    root = job.comments[0]
    assert root.parentId is None
    assert root.body == "Legacy notes blob"
    assert root.editedAt is None
    assert root.createdAt
    assert root.id

    conn2 = get_db_connection(db_path)
    try:
        assert get_schema_version(conn2) == CURRENT_SCHEMA_VERSION
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(jobs)")}
        assert "comments" in cols
        row = conn2.execute("SELECT comment, comments FROM jobs WHERE id = 1").fetchone()
        assert (row[0] or "").strip() == ""
        persisted = json.loads(row[1])
        assert len(persisted) == 1
        assert persisted[0]["body"] == "Legacy notes blob"
    finally:
        conn2.close()


def test_seed_nonempty_comment_becomes_root_comment(tmp_path):
    db_str = _fresh_db(tmp_path)
    job1 = next(j for j in get_jobs(db_str, archived_filter="all") if j.id == 1)
    assert len(job1.comments) >= 1
    assert job1.comments[0].body == "Excellent match. Framework matches 100%."
    assert job1.comments[0].parentId is None
    assert job1.comments[0].editedAt is None


# ---------------------------------------------------------------------------
# Slice 3: Post root Job Comment
# ---------------------------------------------------------------------------


def test_add_job_comment_creates_root_and_logs(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)

    updated = add_job_comment(job_id, "Phone screen next week", db_path=db_str)

    assert updated is not None
    assert len(updated.comments) == 1
    root = updated.comments[0]
    assert root.parentId is None
    assert root.body == "Phone screen next week"
    assert root.editedAt is None
    assert root.createdAt
    assert "Comment added" in [e.message for e in updated.activityLog]

    reloaded = get_job(job_id, db_str)
    assert len(reloaded.comments) == 1
    assert reloaded.comments[0].body == "Phone screen next week"


def test_add_job_comment_rejects_whitespace_without_log(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    before = get_job(job_id, db_str)

    with pytest.raises(ValueError, match="empty|whitespace|blank"):
        add_job_comment(job_id, "   \n\t  ", db_path=db_str)

    after = get_job(job_id, db_str)
    assert after.comments == before.comments
    assert len(after.activityLog) == len(before.activityLog)


def test_add_job_comment_rejects_over_length(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)

    with pytest.raises(ValueError, match="2,?000|too long|max"):
        add_job_comment(job_id, "x" * 2001, db_path=db_str)

    assert get_job(job_id, db_str).comments == []


def test_add_job_comment_missing_job_returns_none(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    assert add_job_comment(99999, "Hello", db_path=db_str) is None


# ---------------------------------------------------------------------------
# Slice 4: HTTP API
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    test_db = tmp_path / "api.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    return TestClient(app), test_db_str


def test_post_job_comment_endpoint(api_client):
    client, _ = api_client
    response = client.get("/api/jobs")
    jobs = response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    before = len(job1["comments"])

    post = client.post("/api/jobs/1/comments", json={"body": "Verified API testing framework."})
    assert post.status_code == 200
    updated = post.json()
    assert len(updated["comments"]) == before + 1
    assert updated["comments"][-1]["body"] == "Verified API testing framework."
    assert updated["comments"][-1]["parentId"] is None
    assert "Comment added" in [e["message"] for e in updated["activityLog"]]

    again = client.get("/api/jobs")
    job1_updated = next(j for j in again.json() if j["id"] == 1)
    assert job1_updated["comments"][-1]["body"] == "Verified API testing framework."


def test_post_job_comment_rejects_whitespace(api_client):
    client, _ = api_client
    response = client.post("/api/jobs/1/comments", json={"body": "   "})
    assert response.status_code == 422


def test_post_job_comment_rejects_over_length(api_client):
    client, _ = api_client
    response = client.post("/api/jobs/1/comments", json={"body": "x" * 2001})
    assert response.status_code == 422


def test_post_job_comment_nonexistent(api_client):
    client, _ = api_client
    response = client.post("/api/jobs/999/comments", json={"body": "No job here"})
    assert response.status_code == 404
    assert response.json() == {"message": "Job not found"}


def test_post_comment_save_failed_activity_message(api_client):
    client, _ = api_client
    response = client.post(
        "/api/jobs/1/activity-log",
        json={"message": "Comment save failed · HTTP error 503"},
    )
    assert response.status_code == 200
    assert "Comment save failed · HTTP error 503" in [
        e["message"] for e in response.json()["activityLog"]
    ]


def test_put_job_comment_endpoint(api_client):
    client, _ = api_client
    post = client.post("/api/jobs/1/comments", json={"body": "Before edit"})
    assert post.status_code == 200
    comment = post.json()["comments"][-1]
    created_at = comment["createdAt"]

    put = client.put(
        f"/api/jobs/1/comments/{comment['id']}",
        json={"body": "After edit"},
    )
    assert put.status_code == 200
    updated = put.json()
    edited = next(c for c in updated["comments"] if c["id"] == comment["id"])
    assert edited["body"] == "After edit"
    assert edited["createdAt"] == created_at
    assert edited["editedAt"]
    assert "Comment edited" in [e["message"] for e in updated["activityLog"]]
    assert not any("After edit" in e["message"] for e in updated["activityLog"])


def test_put_job_comment_rejects_whitespace(api_client):
    client, _ = api_client
    post = client.post("/api/jobs/1/comments", json={"body": "Keep"})
    comment_id = post.json()["comments"][-1]["id"]
    response = client.put(f"/api/jobs/1/comments/{comment_id}", json={"body": "   "})
    assert response.status_code == 422


def test_put_job_comment_rejects_over_length(api_client):
    client, _ = api_client
    post = client.post("/api/jobs/1/comments", json={"body": "Keep"})
    comment_id = post.json()["comments"][-1]["id"]
    response = client.put(
        f"/api/jobs/1/comments/{comment_id}",
        json={"body": "x" * 2001},
    )
    assert response.status_code == 422


def test_put_job_comment_missing_job_or_comment(api_client):
    client, _ = api_client
    post = client.post("/api/jobs/1/comments", json={"body": "Keep"})
    comment_id = post.json()["comments"][-1]["id"]

    missing_job = client.put(
        f"/api/jobs/999/comments/{comment_id}",
        json={"body": "Nope"},
    )
    assert missing_job.status_code == 404
    assert missing_job.json() == {"message": "Job not found"}

    missing_comment = client.put(
        "/api/jobs/1/comments/cdoesnotexist",
        json={"body": "Nope"},
    )
    assert missing_comment.status_code == 404
    assert missing_comment.json() == {"message": "Comment not found"}


# ---------------------------------------------------------------------------
# Slice 5: Drawer wiring (static surface)
# ---------------------------------------------------------------------------


def test_drawer_posts_root_via_comments_endpoint():
    drawer = read_drawer_controller()
    start = drawer.find("function postJobComment(")
    assert start != -1
    body = drawer[start : start + 1600]
    assert "/comments" in body
    assert '"body"' in body or "body:" in body
    assert "Comment save failed" in body
    assert "Notes save failed" not in body


def test_drawer_lists_existing_comments_under_notes_heading():
    drawer = read_drawer_controller()
    assert "Notes / Comments" in drawer
    assert "job.comments" in drawer or "(job.comments" in drawer
    assert "drawer-comment-text" in drawer
    assert "drawer-comments-list" in drawer or "comment-thread" in drawer


def test_drawer_inline_edit_posts_via_put_comments_endpoint():
    drawer = read_drawer_controller()
    assert "startEditJobComment" in drawer
    assert "cancelEditJobComment" in drawer
    assert "postEditJobComment" in drawer
    start = drawer.find("function postEditJobComment(")
    assert start != -1
    body = drawer[start : start + 1800]
    assert "/comments/" in body
    assert "method: 'PUT'" in body or 'method: "PUT"' in body
    assert "Comment edited" not in body or "Comment save failed" in body
    assert "Comment save failed" in body


# ---------------------------------------------------------------------------
# Slice 6: Inline edit Job Comment (#189)
# ---------------------------------------------------------------------------


def test_update_job_comment_edits_body_keeps_created_at_and_logs(tmp_path):
    from src.db import add_job_comment, update_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    created = add_job_comment(job_id, "Original note", db_path=db_str)
    root = created.comments[0]
    original_created = root.createdAt

    updated = update_job_comment(job_id, root.id, "Fixed note", db_path=db_str)

    assert updated is not None
    assert len(updated.comments) == 1
    edited = updated.comments[0]
    assert edited.id == root.id
    assert edited.body == "Fixed note"
    assert edited.createdAt == original_created
    assert edited.editedAt is not None
    assert edited.editedAt != original_created
    assert "Comment edited" in [e.message for e in updated.activityLog]
    assert not any("Fixed note" in e.message for e in updated.activityLog)

    reloaded = get_job(job_id, db_str)
    assert reloaded.comments[0].body == "Fixed note"
    assert reloaded.comments[0].createdAt == original_created
    assert reloaded.comments[0].editedAt is not None


def test_update_job_comment_rejects_whitespace_without_log(tmp_path):
    from src.db import add_job_comment, update_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    created = add_job_comment(job_id, "Keep me", db_path=db_str)
    before = get_job(job_id, db_str)
    comment_id = created.comments[0].id

    with pytest.raises(ValueError, match="empty|whitespace|blank"):
        update_job_comment(job_id, comment_id, "   \n\t  ", db_path=db_str)

    after = get_job(job_id, db_str)
    assert after.comments[0].body == "Keep me"
    assert after.comments[0].editedAt is None
    assert len(after.activityLog) == len(before.activityLog)


def test_update_job_comment_rejects_over_length(tmp_path):
    from src.db import add_job_comment, update_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    created = add_job_comment(job_id, "Short", db_path=db_str)
    comment_id = created.comments[0].id

    with pytest.raises(ValueError, match="2,?000|too long|max"):
        update_job_comment(job_id, comment_id, "x" * 2001, db_path=db_str)

    after = get_job(job_id, db_str)
    assert after.comments[0].body == "Short"
    assert after.comments[0].editedAt is None


def test_update_job_comment_missing_returns_none(tmp_path):
    from src.db import add_job_comment, update_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    add_job_comment(job_id, "Exists", db_path=db_str)

    assert update_job_comment(99999, "cdoesnotexist", "Nope", db_path=db_str) is None
    assert update_job_comment(job_id, "cdoesnotexist", "Nope", db_path=db_str) is None
    assert get_job(job_id, db_str).comments[0].body == "Exists"
