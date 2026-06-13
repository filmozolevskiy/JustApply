import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from .. import database
from ..pipelines import run_search_pipeline, run_enrichment_pipeline
from ..rate_limiter import scrape_limiter, RateLimitError


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
    """Enrich jobs ready for outreach: source contacts and generate messages."""
    print("Starting promote pipeline...")
    database.init_db()

    all_jobs = database.get_jobs()
    to_promote = [
        j for j in all_jobs
        if j.get("shouldProceed") and j.get("status") == "sourced"
    ]
    print(f"Found {len(to_promote)} jobs ready for outreach.")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    promoted = []
    for job in to_promote:
        print(f"Enriching '{job['title']}' at '{job['company']}'...")
        enriched = await run_enrichment_pipeline(job, log_func=log_sync)
        promoted.append(enriched if enriched else job)

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
