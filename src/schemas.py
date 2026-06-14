from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class OutreachSettings(BaseModel):
    target_russian_speakers: bool = True
    target_recruiters: bool = True

JobStatus = Literal[
    "sourced", "enriching", "enriched", "evaluating",
    "contacted", "applied", "interviewing", "rejected",
]


class Contact(BaseModel):
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
    id: Optional[int] = None
    title: str
    company: str
    size: str = ""
    link: str = ""
    date: str = ""
    location: str = ""
    remoteType: str = ""
    seniority: str = ""
    salary: str = ""
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
    comment: str = ""
    isRecruiter: bool = False
    enrichmentNote: str = ""
