"""Job Comments — post root end-to-end (PRD #185 / issue #186)."""

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
import src.db.connection as _db_connection
from fastapi.testclient import TestClient
from src import db as database
from src.db import add_job, get_job, get_jobs, init_db
from src.db.connection import get_db_connection
from src.db.migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from src.web.server import app

from kanban_js import read_drawer_controller

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


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


# ---------------------------------------------------------------------------
# Slice 7: Two-layer replies (#190)
# ---------------------------------------------------------------------------


def test_add_job_comment_reply_under_root_persists_and_logs(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Root note", db_path=db_str).comments[0]

    updated = add_job_comment(
        job_id, "Follow-up reply", parent_id=root.id, db_path=db_str
    )

    assert updated is not None
    assert len(updated.comments) == 2
    reply = next(c for c in updated.comments if c.parentId == root.id)
    assert reply.body == "Follow-up reply"
    assert reply.editedAt is None
    assert reply.createdAt
    assert reply.parentId == root.id
    assert "Comment added" in [e.message for e in updated.activityLog]
    assert sum(1 for e in updated.activityLog if e.message == "Comment added") == 2

    reloaded = get_job(job_id, db_str)
    assert len(reloaded.comments) == 2
    assert any(c.parentId == root.id and c.body == "Follow-up reply" for c in reloaded.comments)
    roots = [c for c in reloaded.comments if c.parentId is None]
    assert len(roots) == 1


def test_add_job_comment_rejects_reply_to_reply(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Root", db_path=db_str).comments[0]
    reply = add_job_comment(
        job_id, "First reply", parent_id=root.id, db_path=db_str
    ).comments[-1]
    before = get_job(job_id, db_str)

    with pytest.raises(ValueError, match="reply|two.?layer|nested|depth"):
        add_job_comment(job_id, "Third layer", parent_id=reply.id, db_path=db_str)

    after = get_job(job_id, db_str)
    assert len(after.comments) == len(before.comments)
    assert len(after.activityLog) == len(before.activityLog)


def test_add_job_comment_rejects_missing_parent(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    add_job_comment(job_id, "Root", db_path=db_str)
    before = get_job(job_id, db_str)

    with pytest.raises(ValueError, match="parent|not found"):
        add_job_comment(job_id, "Orphan", parent_id="cdoesnotexist", db_path=db_str)

    after = get_job(job_id, db_str)
    assert len(after.comments) == len(before.comments)
    assert len(after.activityLog) == len(before.activityLog)


def test_add_job_comment_reply_rejects_whitespace_and_over_length(tmp_path):
    from src.db import add_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Root", db_path=db_str).comments[0]
    before = get_job(job_id, db_str)

    with pytest.raises(ValueError, match="empty|whitespace|blank"):
        add_job_comment(job_id, "   ", parent_id=root.id, db_path=db_str)
    with pytest.raises(ValueError, match="2,?000|too long|max"):
        add_job_comment(job_id, "x" * 2001, parent_id=root.id, db_path=db_str)

    after = get_job(job_id, db_str)
    assert len(after.comments) == len(before.comments)
    assert len(after.activityLog) == len(before.activityLog)


def test_post_job_comment_reply_endpoint(api_client):
    client, _ = api_client
    root_post = client.post("/api/jobs/1/comments", json={"body": "API root"})
    assert root_post.status_code == 200
    root_id = root_post.json()["comments"][-1]["id"]
    roots_before = sum(
        1 for c in root_post.json()["comments"] if c.get("parentId") in (None, "")
    )

    reply_post = client.post(
        "/api/jobs/1/comments",
        json={"body": "API reply", "parentId": root_id},
    )
    assert reply_post.status_code == 200
    updated = reply_post.json()
    reply = updated["comments"][-1]
    assert reply["body"] == "API reply"
    assert reply["parentId"] == root_id
    assert "Comment added" in [e["message"] for e in updated["activityLog"]]
    roots_after = sum(
        1 for c in updated["comments"] if c.get("parentId") in (None, "")
    )
    assert roots_after == roots_before


def test_post_job_comment_rejects_reply_to_reply(api_client):
    client, _ = api_client
    root_id = client.post("/api/jobs/1/comments", json={"body": "Root"}).json()[
        "comments"
    ][-1]["id"]
    reply_id = client.post(
        "/api/jobs/1/comments",
        json={"body": "Reply", "parentId": root_id},
    ).json()["comments"][-1]["id"]

    nested = client.post(
        "/api/jobs/1/comments",
        json={"body": "Too deep", "parentId": reply_id},
    )
    assert nested.status_code == 422


def test_drawer_reply_posts_via_comments_endpoint_with_parent_id():
    drawer = read_drawer_controller()
    assert "startReplyJobComment" in drawer
    assert "cancelReplyJobComment" in drawer
    assert "postReplyJobComment" in drawer
    start = drawer.find("function postReplyJobComment(")
    assert start != -1
    body = drawer[start : start + 1800]
    assert "/comments" in body
    assert "parentId" in body
    assert "Comment save failed" in body
    # Reply control only on roots — replies must not offer Reply.
    assert "data-start-reply" in drawer or "startReplyJobComment(" in drawer
    render_start = drawer.find("function renderBubble(")
    assert render_start != -1
    render_body = drawer[render_start : render_start + 2200]
    assert "isReply" in render_body
    assert "Reply" in render_body
    # Reply button gated so nested bubbles do not get it
    assert "isReply" in render_body and (
        "!isReply" in render_body or "isReply ?" in render_body or "if (!isReply" in render_body
    )


# ---------------------------------------------------------------------------
# Slice 8: Delete with confirm + cascade (#192)
# ---------------------------------------------------------------------------


def test_delete_job_comment_root_cascades_replies_and_logs_once(tmp_path):
    from src.db import add_job_comment, delete_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Root note", db_path=db_str).comments[0]
    add_job_comment(job_id, "Reply one", parent_id=root.id, db_path=db_str)
    add_job_comment(job_id, "Reply two", parent_id=root.id, db_path=db_str)
    other = add_job_comment(job_id, "Other root", db_path=db_str).comments[-1]
    before_logs = len(get_job(job_id, db_str).activityLog)

    updated = delete_job_comment(job_id, root.id, db_path=db_str)

    assert updated is not None
    assert len(updated.comments) == 1
    assert updated.comments[0].id == other.id
    assert updated.comments[0].body == "Other root"
    assert sum(1 for e in updated.activityLog if e.message == "Comment deleted") == 1
    assert len(updated.activityLog) == before_logs + 1
    assert not any("Root note" in e.message for e in updated.activityLog)
    assert not any("Reply" in e.message for e in updated.activityLog)

    reloaded = get_job(job_id, db_str)
    assert len(reloaded.comments) == 1
    assert reloaded.comments[0].id == other.id


def test_delete_job_comment_solo_root_removes_only_that_comment(tmp_path):
    from src.db import add_job_comment, delete_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Solo root", db_path=db_str).comments[0]
    other = add_job_comment(job_id, "Keep me", db_path=db_str).comments[-1]

    updated = delete_job_comment(job_id, root.id, db_path=db_str)

    assert updated is not None
    assert [c.id for c in updated.comments] == [other.id]
    assert "Comment deleted" in [e.message for e in updated.activityLog]


def test_delete_job_comment_reply_leaves_root_and_logs_once(tmp_path):
    from src.db import add_job_comment, delete_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    root = add_job_comment(job_id, "Root stays", db_path=db_str).comments[0]
    reply = add_job_comment(
        job_id, "Drop reply", parent_id=root.id, db_path=db_str
    ).comments[-1]
    sibling = add_job_comment(
        job_id, "Sibling reply", parent_id=root.id, db_path=db_str
    ).comments[-1]

    updated = delete_job_comment(job_id, reply.id, db_path=db_str)

    assert updated is not None
    ids = {c.id for c in updated.comments}
    assert root.id in ids
    assert sibling.id in ids
    assert reply.id not in ids
    assert sum(1 for e in updated.activityLog if e.message == "Comment deleted") == 1


def test_delete_job_comment_missing_returns_none(tmp_path):
    from src.db import add_job_comment, delete_job_comment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    add_job_comment(job_id, "Exists", db_path=db_str)

    assert delete_job_comment(99999, "cdoesnotexist", db_path=db_str) is None
    assert delete_job_comment(job_id, "cdoesnotexist", db_path=db_str) is None
    assert get_job(job_id, db_str).comments[0].body == "Exists"


def test_delete_job_comment_endpoint_cascades_root(api_client):
    client, _ = api_client
    root_id = client.post("/api/jobs/1/comments", json={"body": "API root"}).json()[
        "comments"
    ][-1]["id"]
    client.post(
        "/api/jobs/1/comments",
        json={"body": "API reply", "parentId": root_id},
    )
    before = client.get("/api/jobs").json()
    job1 = next(j for j in before if j["id"] == 1)
    roots_before = sum(
        1 for c in job1["comments"] if c.get("parentId") in (None, "")
    )

    deleted = client.delete(f"/api/jobs/1/comments/{root_id}")
    assert deleted.status_code == 200
    updated = deleted.json()
    assert not any(c["id"] == root_id for c in updated["comments"])
    assert not any(c.get("parentId") == root_id for c in updated["comments"])
    roots_after = sum(
        1 for c in updated["comments"] if c.get("parentId") in (None, "")
    )
    assert roots_after == roots_before - 1
    assert "Comment deleted" in [e["message"] for e in updated["activityLog"]]
    assert not any("API root" in e["message"] for e in updated["activityLog"])


def test_delete_job_comment_endpoint_reply_only(api_client):
    client, _ = api_client
    root_id = client.post("/api/jobs/1/comments", json={"body": "Keep root"}).json()[
        "comments"
    ][-1]["id"]
    reply_id = client.post(
        "/api/jobs/1/comments",
        json={"body": "Gone reply", "parentId": root_id},
    ).json()["comments"][-1]["id"]

    deleted = client.delete(f"/api/jobs/1/comments/{reply_id}")
    assert deleted.status_code == 200
    updated = deleted.json()
    assert any(c["id"] == root_id for c in updated["comments"])
    assert not any(c["id"] == reply_id for c in updated["comments"])
    assert "Comment deleted" in [e["message"] for e in updated["activityLog"]]


def test_delete_job_comment_endpoint_missing_job_or_comment(api_client):
    client, _ = api_client
    post = client.post("/api/jobs/1/comments", json={"body": "Keep"})
    comment_id = post.json()["comments"][-1]["id"]

    missing_job = client.delete(f"/api/jobs/999/comments/{comment_id}")
    assert missing_job.status_code == 404
    assert missing_job.json() == {"message": "Job not found"}

    missing_comment = client.delete("/api/jobs/1/comments/cdoesnotexist")
    assert missing_comment.status_code == 404
    assert missing_comment.json() == {"message": "Comment not found"}

    still = client.get("/api/jobs").json()
    job1 = next(j for j in still if j["id"] == 1)
    assert any(c["id"] == comment_id for c in job1["comments"])


def test_build_delete_comment_confirm_message_copy():
    """Confirm copy: cascade warns N replies; solo root/reply uses Delete this note?"""
    result = _run_node(
        """
        import { buildDeleteCommentConfirmMessage } from './src/web/static/js/drawerController.js';

        const comments = [
          { id: 'r1', parentId: null, body: 'Root' },
          { id: 'r1a', parentId: 'r1', body: 'A' },
          { id: 'r1b', parentId: 'r1', body: 'B' },
          { id: 'r2', parentId: null, body: 'Solo' },
        ];
        const cascade = buildDeleteCommentConfirmMessage(
          { id: 'r1', parentId: null },
          comments,
        );
        if (cascade !== 'Delete this note and its 2 replies?') process.exit(1);

        const solo = buildDeleteCommentConfirmMessage(
          { id: 'r2', parentId: null },
          comments,
        );
        if (solo !== 'Delete this note?') process.exit(2);

        const reply = buildDeleteCommentConfirmMessage(
          { id: 'r1a', parentId: 'r1' },
          comments,
        );
        if (reply !== 'Delete this note?') process.exit(3);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_delete_posts_via_delete_comments_endpoint():
    drawer = read_drawer_controller()
    assert "deleteJobComment" in drawer
    assert "buildDeleteCommentConfirmMessage" in drawer
    start = drawer.find("function deleteJobComment(")
    assert start != -1
    body = drawer[start : start + 2200]
    assert "confirm(" in body or "window.confirm" in body
    assert "buildDeleteCommentConfirmMessage" in body
    assert "/comments/" in body
    assert "method: 'DELETE'" in body or 'method: "DELETE"' in body
    assert "onJobMutated()" in body
    assert "Comment delete failed" in body or "Comment save failed" in body
    # Delete control on bubbles
    assert "data-delete-comment" in drawer or "deleteJobComment(" in drawer
    render_start = drawer.find("function renderBubble(")
    assert render_start != -1
    render_body = drawer[render_start : render_start + 2500]
    assert "Delete" in render_body
    assert "deleteJobComment" in render_body or "data-delete-comment" in render_body
