import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

# Add project root to path so modules are importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from . import database
from src.core.scraper import scrape_linkedin_jobs
from src.core.matcher import load_resume, evaluate_job
from src.core.outreach import source_contacts


LOCK_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_trigger")


async def run_search(
    position: str,
    sites: list = None,
    mock_eval: bool = False,
    allowed_remote_types: list = None
) -> list:
    """Search for jobs using Bright Data scraper, evaluate via LLM, save to SQLite."""
    is_mock_scraper = os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    is_real = (not mock_eval) or (not is_mock_scraper)
    if is_real:
        import time
        current_time = time.time()
        if os.path.exists(LOCK_FILE_PATH):
            try:
                with open(LOCK_FILE_PATH, "r") as f:
                    content = f.read().strip()
                    if content:
                        last_time = float(content)
                        elapsed = current_time - last_time
                        if elapsed < 60:
                            print(f"Warning: Rate limit active. Please wait {int(60 - elapsed)} seconds.", file=sys.stderr)
                            sys.exit(1)
            except (ValueError, OSError):
                pass
        
        try:
            with open(LOCK_FILE_PATH, "w") as f:
                f.write(str(current_time))
        except OSError:
            pass

    print(f"Starting search pipeline for position: {position}")

    def log_sync(msg: str, level: str = "info"):
        print(f"[{level.upper()}] {msg}", file=sys.stderr)

    jobs = await scrape_linkedin_jobs(
        query=position,
        location="Remote",
        remote_types=allowed_remote_types,
        log_func=log_sync,
    )
    print(f"Found {len(jobs)} matching jobs.")

    resume_name = position.lower().replace("/", "_").replace(" ", "_")
    if not resume_name.endswith(".md"):
        resume_name += ".md"

    resume_content = None
    if not mock_eval:
        try:
            resume_content = load_resume(resume_name)
        except FileNotFoundError:
            try:
                resume_content = load_resume("qa.md")
            except FileNotFoundError:
                print("Warning: No resume found. Skipping LLM evaluation.", file=sys.stderr)

    database.init_db()
    saved = []
    for job in jobs:
        title = job.get("title") or ""
        company = job.get("company") or ""
        link = job.get("link") or ""
        if database.job_exists(title, company, link):
            print(f"Skipping duplicate job: '{title}' at '{company}'", file=sys.stderr)
            continue

        job["resumeUsed"] = resume_name

        if mock_eval or resume_content is None:
            job.setdefault("matchScore", 0)
            job.setdefault("matchType", "")
            job.setdefault("shouldProceed", False)
            job.setdefault("strengths", [])
            job.setdefault("gaps", [])
            
            from src.core.matcher import check_recruiter_by_name
            if check_recruiter_by_name(company):
                job["isRecruiter"] = True
                job["gaps"].append("Posted by a recruiting agency/staffing firm")
            else:
                job["isRecruiter"] = False
        else:
            evaluation = await evaluate_job(job, resume_content, allowed_remote_types=allowed_remote_types)
            if evaluation:
                job["matchScore"] = evaluation.get("matchScore", 0)
                job["matchType"] = evaluation.get("matchType", "")
                job["shouldProceed"] = evaluation.get("shouldProceed", False)
                job["strengths"] = evaluation.get("strengths", [])
                job["gaps"] = evaluation.get("gaps", [])
                if "remoteType" in evaluation:
                    job["remoteType"] = evaluation["remoteType"]
                if "summary" in evaluation:
                    job["description"] = evaluation["summary"]
                job["isRecruiter"] = evaluation.get("isRecruiter", False)
                if evaluation.get("salary"):
                    job["salary"] = evaluation["salary"]

        job_id = database.add_job(job)
        if job_id is not None:
            job["id"] = job_id
            saved.append(job)
            print(f"Saved: {job.get('title')} at {job.get('company')} (id={job_id})")

    print(f"Search complete. {len(saved)} jobs saved to database.")
    return saved


async def run_promote() -> list:
    """Source outreach contacts for jobs that are ready to proceed."""
    print("Starting promote pipeline...")
    database.init_db()

    all_jobs = database.get_jobs()
    to_promote = [
        j for j in all_jobs
        if j.get("shouldProceed") and j.get("status") == "sourced"
    ]
    print(f"Found {len(to_promote)} jobs ready for outreach.")

    promoted = []
    for job in to_promote:
        print(f"Sourcing contacts for '{job['title']}' at '{job['company']}'...")
        contacts = await source_contacts(job)
        if contacts:
            print(f"  Found {len(contacts)} contact(s). First: {contacts[0].get('name')}")
        else:
            print("  No contacts found.")
        promoted.append(job)

    print(f"Promote complete. Processed {len(promoted)} jobs.")
    return promoted


def main():
    parser = argparse.ArgumentParser(description="Job Hunter CLI")
    parser.add_argument("--search", metavar="POSITION", help="Search and evaluate jobs for a position")
    parser.add_argument("--promote", action="store_true", help="Source contacts for jobs ready to proceed")
    parser.add_argument("--sites", help="Comma-separated list of job sites (unused, reserved for future use)")
    args = parser.parse_args()

    if args.search:
        asyncio.run(run_search(args.search))
    elif args.promote:
        asyncio.run(run_promote())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
