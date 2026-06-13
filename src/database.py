import sqlite3
import json
import os

VALID_STATUSES = frozenset({
    "sourced", "enriching", "enriched", "evaluating",
    "contacted", "applied", "interviewing", "rejected",
})

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "job_tracker.db")

def get_db_connection(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _parse_job_row(row) -> dict:
    job = dict(row)
    for field in ("strengths", "gaps", "contacts"):
        raw = job.get(field)
        try:
            job[field] = json.loads(raw) if raw else []
        except Exception:
            job[field] = []
    job["shouldProceed"] = bool(job["shouldProceed"])
    job["isRecruiter"] = bool(job.get("isRecruiter", 0))
    return job

def _seed_db(cursor):
    seed_data = [
        {
            "id": 1,
            "title": "Senior QA Automation Engineer",
            "company": "TechCorp",
            "size": "100-500",
            "link": "https://linkedin.com/jobs/123",
            "date": "2026-06-05",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$130k - $160k",
            "description": "We are looking for a Senior QA Automation Engineer to build and execute end-to-end testing strategies. You will design automation frameworks using Python and Pytest, integration into GitHub actions, and lead testing standards.",
            "matchScore": 94,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "sourced",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Highly proficient in Python & Pytest", "Extensive CI/CD pipeline automation", "Playwright & Selenium Frameworks"]),
            "gaps": json.dumps(["No direct experience with WebUSB", "AWS Cloud Practitioner certification preferred"]),
            "contacts": json.dumps([
                {"name": "Jane Doe", "role": "VP Engineering", "linkedin": "https://linkedin.com/in/janedoe", "contacted": False},
                {"name": "John Smith", "role": "Recruiting Coordinator", "linkedin": "https://linkedin.com/in/johnsmith", "contacted": False}
            ]),
            "outreachMessage": "Hi Jane,\n\nI saw your listing for a Senior QA Automation Engineer at TechCorp. With my deep background in building Python/Pytest framework architectures and setting up robust CI/CD pipelines, I believe I can hit the ground running. I'd love to learn more about TechCorp's engineering goals.\n\nBest,\nCandidate",
            "comment": "Excellent match. Framework matches 100%."
        },
        {
            "id": 2,
            "title": "Technical Project & Delivery Manager",
            "company": "InnovateHQ",
            "size": "50-200",
            "link": "https://linkedin.com/jobs/124",
            "date": "2026-06-04",
            "location": "New York, NY",
            "remoteType": "hybrid",
            "seniority": "senior",
            "salary": "$140k - $170k",
            "description": "InnovateHQ is seeking a Technical Project Manager to coordinate cross-functional agile sprints, manage stakeholder delivery milestones, and ensure tight integration of engineering and product roadmaps.",
            "matchScore": 88,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "sourced",
            "resumeUsed": "project_manager.md",
            "strengths": json.dumps(["Expert Scrum Master with 5+ years experience", "Strong technical background in Python systems", "Stakeholder communications"]),
            "gaps": json.dumps(["Prior experience at Series A startups is not documented"]),
            "contacts": json.dumps([
                {"name": "Marcus Vance", "role": "Director of Product", "linkedin": "https://linkedin.com/in/marcusvance", "contacted": False},
                {"name": "Alice Adams", "role": "Talent Lead", "linkedin": "https://linkedin.com/in/aliceadams", "contacted": False}
            ]),
            "outreachMessage": "Dear Marcus,\n\nI noticed InnovateHQ is hiring a Technical Project Manager. Given my extensive delivery management experience aligning engineering teams with product milestones, I'm excited about this opportunity. Let's connect!\n\nBest regards,\nCandidate",
            "comment": "Need to verify Series A startup history before applying."
        },
        {
            "id": 3,
            "title": "Data & BI Analyst",
            "company": "FinanceFlow",
            "size": "1000+",
            "link": "https://linkedin.com/jobs/125",
            "date": "2026-06-03",
            "location": "Charlotte, NC",
            "remoteType": "in office",
            "seniority": "mid",
            "salary": "$100k - $120k",
            "description": "FinanceFlow is hiring a Data Analyst to compile SQL reporting queries, construct Tableau dashboards, and deliver weekly metrics to financial compliance executives.",
            "matchScore": 75,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "contacted",
            "resumeUsed": "data_analyst.md",
            "strengths": json.dumps(["Excellent SQL database experience", "Experienced with Tableau and PowerBI", "Detail-oriented financial analysis"]),
            "gaps": json.dumps(["No direct experience with FinTech compliance frameworks"]),
            "contacts": json.dumps([
                {"name": "Sophia Patel", "role": "Data Analytics Lead", "linkedin": "https://linkedin.com/in/sophiapatel", "contacted": True},
                {"name": "Robert Miller", "role": "FinTech Recruiter", "linkedin": "https://linkedin.com/in/robertmiller", "contacted": False}
            ]),
            "outreachMessage": "Hi Sophia,\n\nI'm reaching out regarding the Data & BI Analyst vacancy. I have a proven track record creating high-impact SQL/Tableau dashboards. I'd love to help FinanceFlow drive metrics.\n\nThanks,\nCandidate",
            "comment": "Sophia responded! Phone screen scheduled next week."
        },
        {
            "id": 4,
            "title": "QA Automation Specialist",
            "company": "GameStudio",
            "size": "200-500",
            "link": "https://linkedin.com/jobs/126",
            "date": "2026-06-01",
            "location": "Austin, TX",
            "remoteType": "remote",
            "seniority": "mid",
            "salary": "$90k - $110k",
            "description": "Join our game build testing team. You will automate functional regression testing for web services and gameplay configurations using Python scripts.",
            "matchScore": 92,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "interviewing",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Automation framework expert", "Fast debugging of Python regression scripts"]),
            "gaps": json.dumps(["No experience with specific Game engines (Unreal/Unity)"]),
            "contacts": json.dumps([
                {"name": "Alex Mercer", "role": "QA Manager", "linkedin": "https://linkedin.com/in/alexmercer", "contacted": True},
                {"name": "Emma Stone", "role": "HR Business Partner", "linkedin": "https://linkedin.com/in/emmastone", "contacted": True}
            ]),
            "outreachMessage": "Hi Alex,\n\nI'd love to join GameStudio as a QA Automation Specialist. My scripting experience with Python makes me an excellent fit for your functional regression goals.\n\nBest,\nCandidate",
            "comment": "Completed round 1 interview. Focus was Python scripting."
        },
        {
            "id": 5,
            "title": "Agile Scrum Master",
            "company": "GlobalSystems",
            "size": "5000+",
            "link": "https://linkedin.com/jobs/127",
            "date": "2026-05-28",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$120k - $140k",
            "description": "Seeking a senior scrum master to facilitate agile practices across 4 distributed software teams. Enterprise scale delivery planning required.",
            "matchScore": 68,
            "matchType": "no-match",
            "shouldProceed": 0,
            "status": "rejected",
            "resumeUsed": "project_manager.md",
            "strengths": json.dumps(["Scrum Master Certified"]),
            "gaps": json.dumps(["No experience with SAFe framework at enterprise scale"]),
            "contacts": json.dumps([
                {"name": "Evelyn Ross", "role": "HR Partner", "linkedin": "https://linkedin.com/in/evelynross", "contacted": False}
            ]),
            "outreachMessage": "",
            "comment": "Enterprise SAFe requirement is a hard blocker."
        },
        {
            "id": 6,
            "title": "QA Lead",
            "company": "AppStart",
            "size": "10-50",
            "link": "https://linkedin.com/jobs/128",
            "date": "2026-06-06",
            "location": "San Francisco, CA",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$150k - $180k",
            "description": "AppStart is seeking our first QA Lead to establish our test pipeline. You will be responsible for defining automation protocols, running manual exploratory testing, and implementing CI tools.",
            "matchScore": 91,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "sourced",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Startup experience (first QA hire)", "Established full-suite testing protocols from scratch", "Fast API testing"]),
            "gaps": json.dumps(["No mobile testing experience mentioned"]),
            "contacts": json.dumps([
                {"name": "Tariq Mahmood", "role": "Co-Founder / CTO", "linkedin": "https://linkedin.com/in/tariqmahmood", "contacted": False},
                {"name": "Liam Neeson", "role": "Talent Specialist", "linkedin": "https://linkedin.com/in/liamneeson", "contacted": False}
            ]),
            "outreachMessage": "Hi Tariq,\n\nCongratulations on expanding your engineering team. As a QA Lead who has previously built testing infrastructures for early stage startups, I would love to help AppStart structure its automation strategy.\n\nBest,\nCandidate",
            "comment": "Tariq is active on LinkedIn posting engineering updates."
        },
        {
            "id": 7,
            "title": "QA Automation Contractor",
            "company": "Fuze HR Solutions",
            "size": "50-200",
            "link": "https://linkedin.com/jobs/129",
            "date": "2026-06-07",
            "location": "Toronto, ON",
            "remoteType": "hybrid",
            "seniority": "mid",
            "salary": "$70 - $80 / hr",
            "description": "Our client, a leading financial institution, is seeking a QA Automation Contractor to join their digital banking testing team. You will write automated test scripts in Python and execute regressions.",
            "matchScore": 65,
            "matchType": "no-match",
            "shouldProceed": 0,
            "status": "sourced",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Python scripting background", "Experience with QA regression testing"]),
            "gaps": json.dumps(["Posted by a recruiting agency/staffing firm"]),
            "contacts": json.dumps([]),
            "outreachMessage": "",
            "comment": "Recruiter company. 15-point penalty applied.",
            "isRecruiter": 1
        }
    ]
    for job in seed_data:
        job.setdefault("isRecruiter", 0)
        cursor.execute("""
            INSERT INTO jobs (
                id, title, company, size, link, date, location, remoteType, seniority, salary,
                description, matchScore, matchType, shouldProceed, status, resumeUsed,
                strengths, gaps, contacts, outreachMessage, comment, isRecruiter
            ) VALUES (
                :id, :title, :company, :size, :link, :date, :location, :remoteType, :seniority, :salary,
                :description, :matchScore, :matchType, :shouldProceed, :status, :resumeUsed,
                :strengths, :gaps, :contacts, :outreachMessage, :comment, :isRecruiter
            )
        """, job)

def init_db(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            size TEXT,
            link TEXT,
            date TEXT,
            location TEXT,
            remoteType TEXT,
            seniority TEXT,
            salary TEXT,
            description TEXT,
            matchScore INTEGER,
            matchType TEXT,
            shouldProceed INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'sourced',
            resumeUsed TEXT,
            strengths TEXT,
            gaps TEXT,
            contacts TEXT,
            outreachMessage TEXT,
            comment TEXT,
            isRecruiter INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    # Migration: Add isRecruiter column to existing database if missing
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN isRecruiter INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass

    cursor.execute("SELECT COUNT(*) FROM jobs")
    count = cursor.fetchone()[0]
    if count == 0:
        _seed_db(cursor)
        conn.commit()
    conn.close()

def get_jobs(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [_parse_job_row(r) for r in rows]

def update_job_status(job_id, status, db_path=None):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Valid values: {sorted(VALID_STATUSES)}")
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)

def update_job_comment(job_id, comment, db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET comment = ? WHERE id = ?", (comment, job_id))
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)

def update_contact_status(job_id, contact_idx, contacted, db_path=None):
    """Mark a single contact as contacted/not-contacted. Returns updated job or None."""
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    job = dict(row)
    try:
        contacts = json.loads(job.get("contacts") or "[]")
    except Exception:
        contacts = []

    if contact_idx < 0 or contact_idx >= len(contacts):
        conn.close()
        return None

    contacts[contact_idx]["contacted"] = bool(contacted)

    # Auto-promote sourced/enriching/enriched → contacted when a contact is first marked contacted
    status = job["status"]
    if contacted and status in ("sourced", "enriching", "enriched"):
        status = "contacted"

    cursor.execute(
        "UPDATE jobs SET contacts = ?, status = ? WHERE id = ?",
        (json.dumps(contacts), status, job_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    updated = cursor.fetchone()
    conn.close()
    return _parse_job_row(updated)


def get_job(job_id, db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)


def start_enrichment(job_id, db_path=None):
    """Mark a job as enriching. Returns updated job or None if not found."""
    return update_job_status(job_id, "enriching", db_path)


def enrich_job(job_id, contacts, outreach_message, db_path=None):
    """Persist contacts, outreach message, and set status to enriched."""
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    cursor.execute(
        "UPDATE jobs SET contacts = ?, outreachMessage = ?, status = 'enriched' WHERE id = ?",
        (json.dumps(contacts), outreach_message, job_id),
    )
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return _parse_job_row(row) if row else None


def job_exists(title, company, link=None, db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if link:
        cursor.execute("SELECT id FROM jobs WHERE link = ?", (link,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return True
    cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (title, company))
    existing = cursor.fetchone()
    conn.close()
    return existing is not None


def add_job(job, db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    title = job.get("title") or job.get("Job title") or ""
    company = job.get("company") or job.get("Company + Company size") or ""
    link = job.get("link") or job.get("Posting link") or ""

    if not title.strip() and not company.strip():
        conn.close()
        return None

    if link:
        cursor.execute("SELECT id FROM jobs WHERE link = ?", (link,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return existing[0]

    cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (title, company))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing[0]

    cursor.execute("""
        INSERT INTO jobs (
            title, company, size, link, date, location, remoteType, seniority, salary,
            description, matchScore, matchType, shouldProceed, status, resumeUsed,
            strengths, gaps, contacts, outreachMessage, comment, isRecruiter
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        title,
        company,
        job.get("size") or "",
        link,
        job.get("date") or job.get("Posting date") or "",
        job.get("location") or job.get("Location + Remote type (in office, hybrid, remote)") or "",
        job.get("remoteType") or "",
        job.get("seniority") or job.get("Seniority type (junior, mid, senior)") or "",
        job.get("salary") or job.get("Salary type") or "",
        job.get("description") or job.get("Short description") or "",
        job.get("matchScore") or 0,
        job.get("matchType") or "",
        1 if job.get("shouldProceed") or job.get("Should proceed?") else 0,
        job.get("status") or "sourced",
        job.get("resumeUsed") or "",
        json.dumps(job.get("strengths") or []),
        json.dumps(job.get("gaps") or []),
        json.dumps(job.get("contacts") or []),
        job.get("outreachMessage") or "",
        job.get("comment") or job.get("Comment") or "",
        1 if job.get("isRecruiter") else 0
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id
