"""Tests for Job Activity Log DB behavior."""
import os
import sys
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, add_job, get_jobs, update_job_status, enrich_job
from src.db.jobs import update_contact_status


def _fresh_db(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    return db_str


def _get_job(db_str, job_id):
    jobs = get_jobs(db_str)
    return next(j for j in jobs if j.id == job_id)


# --- add_job ---

def test_add_job_creates_found_entry(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA Engineer", "company": "Acme"}, db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Found" in messages


# --- update_job_status ---

def test_update_job_status_logs_move(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA Engineer", "company": "Acme", "status": "scraped"}, db_str)
    update_job_status(job_id, "applied", db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Moved Scraped → Applied" in messages


def test_update_job_status_to_accepted_logs_move(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA Engineer", "company": "Acme", "status": "scraped"}, db_str)
    update_job_status(job_id, "accepted", db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Moved Scraped → Accepted" in messages


def test_update_job_status_same_status_no_log_entry(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA Engineer", "company": "Acme", "status": "scraped"}, db_str)
    before = _get_job(db_str, job_id)
    before_len = len(before.activityLog)
    update_job_status(job_id, "scraped", db_str)
    after = _get_job(db_str, job_id)
    assert len(after.activityLog) == before_len


# --- enrich_job ---

def test_enrich_job_success_logs_contact_count(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    contacts = [
        {"name": "Alice", "url": "https://linkedin.com/in/alice", "contacted": False},
        {"name": "Bob", "url": "https://linkedin.com/in/bob", "contacted": False},
    ]
    enrich_job(job_id, contacts, "Hi!", db_path=db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Enriched · 2 contacts" in messages


def test_enrich_job_single_contact_singular_label(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    contacts = [{"name": "Alice", "url": "https://linkedin.com/in/alice", "contacted": False}]
    enrich_job(job_id, contacts, "Hi!", db_path=db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Enriched · 1 contact" in messages


def test_enrich_job_failure_logs_enrichment_note(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    enrich_job(job_id, [], "", enrichment_note="Apify failed: HTTP 403", db_path=db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Enrichment failed · Apify failed: HTTP 403" in messages


def test_enrich_job_reclassify_logs_reclassified(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    contacts = [
        {"name": "Alice", "url": "https://linkedin.com/in/alice", "contacted": False},
        {"name": "Bob", "url": "https://linkedin.com/in/bob", "contacted": False},
    ]
    enrich_job(job_id, contacts, "Hi!", activity_kind="reclassify", db_path=db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Re-classified · 2 contacts" in messages
    assert not any("Enriched" in m for m in messages)


def test_enrich_job_load_more_logs_new_profiles(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    contacts = [{"name": "Alice", "url": "https://linkedin.com/in/alice", "contacted": False}]
    enrich_job(
        job_id,
        contacts,
        "Hi!",
        activity_kind="load_more",
        new_profile_count=3,
        db_path=db_str,
    )
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Load more contacts · 1 contact (3 new profiles)" in messages


# --- update_contact_status ---

def test_contact_marked_contacted_logs_name(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    contacts = [{"name": "Jane Doe", "url": "https://linkedin.com/in/jane", "contacted": False}]
    enrich_job(job_id, contacts, "Hi!", db_path=db_str)
    update_contact_status(job_id, 0, True, db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert "Marked Jane Doe contacted" in messages


def test_contact_marked_contacted_does_not_change_job_status(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "found"}, db_str)
    contacts = [{"name": "Jane Doe", "url": "https://linkedin.com/in/jane", "contacted": False}]
    enrich_job(job_id, contacts, "Hi!", db_path=db_str)
    # status is "accepted" after enrich — checkbox must NOT change it
    update_contact_status(job_id, 0, True, db_str)
    job = _get_job(db_str, job_id)
    assert job.status == "accepted"


def test_contact_marked_contacted_no_lane_move_in_log(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "found"}, db_str)
    contacts = [{"name": "Jane Doe", "url": "https://linkedin.com/in/jane", "contacted": False}]
    enrich_job(job_id, contacts, "Hi!", db_path=db_str)
    update_contact_status(job_id, 0, True, db_str)
    job = _get_job(db_str, job_id)
    messages = [e.message for e in job.activityLog]
    assert not any("→ Applied" in m for m in messages)


# --- cap at 50 ---

def test_activity_log_capped_at_50_entries(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    # Cycle through statuses to generate many log entries
    statuses = ["applied", "scraped", "applied", "scraped", "applied", "scraped",
                "applied", "scraped", "applied", "scraped"]
    for _ in range(6):  # 6 * 10 = 60 transitions + 1 initial Found = 61 entries attempted
        for s in statuses:
            update_job_status(job_id, s, db_str)
    job = _get_job(db_str, job_id)
    assert len(job.activityLog) <= 50


# --- Job Comment Post (PRD #105) ---

def test_update_job_comment_appends_notes_updated(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    from src.db import update_job_comment

    update_job_comment(job_id, "Phone screen next week", db_str)
    job = _get_job(db_str, job_id)
    assert "Notes updated" in [e.message for e in job.activityLog]


def test_update_outreach_template_appends_outreach_template_updated(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    from src.db.jobs import update_outreach_template

    update_outreach_template(job_id, "recruiter", "Hello ______,", db_path=db_str)
    job = _get_job(db_str, job_id)
    assert "Outreach template updated" in [e.message for e in job.activityLog]


# --- activityLog field on job ---

def test_activity_log_field_is_list_on_all_jobs(tmp_path):
    db_str = _fresh_db(tmp_path)
    jobs = get_jobs(db_str)
    for job in jobs:
        assert isinstance(job.activityLog, list)


def test_activity_log_entries_have_ts_and_message(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    job = _get_job(db_str, job_id)
    assert len(job.activityLog) >= 1
    entry = job.activityLog[0]
    assert entry.ts
    assert entry.message
    assert entry.message == "Found"
