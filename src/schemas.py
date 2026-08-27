from typing import Literal

from pydantic import BaseModel, ConfigDict


class OutreachSettings(BaseModel):
    target_russian_speakers: bool = True
    target_recruiters: bool = True
    short_connection_note: bool = True

JobStatus = Literal[
    "scraped", "matched", "accepted",
    "applied", "interviewing", "rejected",
]


class ActivityLogEntry(BaseModel):
    ts: str
    message: str


class JobComment(BaseModel):
    """A single user-written Job Comment on a job (root or reply)."""

    id: str
    parentId: str | None = None
    body: str
    createdAt: str
    editedAt: str | None = None


class Contact(BaseModel):
    """Outreach contact stored inside Job.contacts JSON.

    ``extra="allow"`` is intentional. Enrichment copies Apify-normalized fields
    such as ``currentPosition`` and ``location`` that are not first-class
    columns, and runtime metadata such as ``contacted_at`` and
    ``contactedElsewhere`` is attached on read. Tightening validation would
    drop these keys on deserialize and break Kanban contact rendering and
    **Contacted Elsewhere** indicators. See ``tests/conftest.py`` fixture
    ``apify_employee_item`` and ``tests/test_contact_schema.py``.
    """

    model_config = ConfigDict(extra="allow")

    name: str = ""
    title: str = ""
    role: str = ""
    url: str = ""
    linkedin: str = ""
    contacted: bool = False
    russian_speaker: bool = False
    is_recruiter: bool = False
    is_job_poster: bool = False


class Job(BaseModel):
    id: int | None = None
    title: str
    company: str
    companyUrl: str = ""
    size: str = ""
    link: str = ""
    date: str = ""
    location: str = ""
    remoteType: str = ""
    seniority: str = ""
    employmentType: str = ""
    salary: str = ""
    annualMin: int | None = None
    annualMax: int | None = None
    annualCurrency: str | None = None
    description: str = ""
    matchScore: int = 0
    matchType: str = ""
    shouldProceed: bool = False
    status: str = ""
    resumeUsed: str = ""
    strengths: list[str] = []
    gaps: list[str] = []
    contacts: list[Contact] = []
    outreachMessage: str = ""
    recruiterOutreachTemplate: str = ""
    russianSpeakerOutreachTemplate: str = ""
    comments: list[JobComment] = []
    isRecruiter: bool = False
    unclassified: bool = False
    batchAttempts: int = 0
    enrichmentNote: str = ""
    enrichmentNoteKind: str = ""
    activityLog: list[ActivityLogEntry] = []
    archived: bool = False
    rejectedAt: str = ""
    autoArchiveExempt: bool = False
    favorited: bool = False
    companyResearch: dict | None = None
