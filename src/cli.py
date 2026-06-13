import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

# Add project root to path so modules are importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from . import database
from .core.outreach import source_contacts
from .pipelines import run_search_pipeline
from .rate_limiter import scrape_limiter, RateLimitError


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
        try:
            scrape_limiter.acquire()
        except RateLimitError as e:
            print(f"Warning: Rate limit active. Please wait {e.wait_seconds} seconds.", file=sys.stderr)
            sys.exit(1)

    resume_name = position.lower().replace("/", "_").replace(" ", "_")
    if not resume_name.endswith(".md"):
        resume_name += ".md"

    def log_sync(msg: str, level: str = "info"):
        print(f"[{level.upper()}] {msg}", file=sys.stderr)

    saved = await run_search_pipeline(
        query=position,
        location="Remote",
        active_resume=resume_name,
        mock_eval=mock_eval,
        allowed_remote_types=allowed_remote_types,
        log_func=log_sync,
    )

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
