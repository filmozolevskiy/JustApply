import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from .. import db as database
from ..service import RateLimitError, promote_sourced_jobs, reassess_all_jobs, reassess_job, search_jobs


def _resume_name_for_position(position: str) -> str:
    resume_name = position.lower().replace("/", "_").replace(" ", "_")
    if not resume_name.endswith(".md"):
        resume_name += ".md"
    return resume_name


async def run_search(
    position: str,
    sites: list = None,
    mock_eval: bool = False,
    allowed_remote_types: list = None
) -> list:
    """Search for jobs using Bright Data scraper, evaluate via LLM, save to SQLite."""
    def log_sync(msg: str, level: str = "info"):
        print(f"[{level.upper()}] {msg}", file=sys.stderr)

    try:
        saved = await search_jobs(
            query=position,
            location="Remote",
            active_resume="general_cv.md",
            mock_eval=mock_eval,
            allowed_remote_types=allowed_remote_types,
            log_func=log_sync,
        )
    except RateLimitError as e:
        print(f"Warning: Rate limit active. Please wait {e.wait_seconds} seconds.", file=sys.stderr)
        sys.exit(1)

    print(f"Search complete. {len(saved)} jobs saved to database.")
    return saved


async def run_reassess(job_id: int | None = None, reassess_all: bool = False) -> list:
    """Re-run Resume Matcher on one job or all active jobs."""
    def log_sync(msg: str, level: str = "info"):
        print(f"[{level.upper()}] {msg}", file=sys.stderr)

    if reassess_all:
        updated = await reassess_all_jobs(log_func=log_sync)
        print(f"Re-assess complete. {len(updated)} jobs updated.")
        return updated

    if job_id is None:
        print("Error: provide a job ID or use --reassess-all.", file=sys.stderr)
        sys.exit(1)

    updated = await reassess_job(job_id, log_func=log_sync)
    print(f"Re-assessed job id={job_id}: score={updated.matchScore}, matchType={updated.matchType}")
    return [updated]


async def run_promote() -> list:
    """Enrich jobs ready for outreach: source contacts and generate messages."""
    print("Starting promote pipeline...")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    promoted = await promote_sourced_jobs(log_func=log_sync)

    print(f"Promote complete. Processed {len(promoted)} jobs.")
    return promoted


def main():
    parser = argparse.ArgumentParser(description="JustApply CLI")
    parser.add_argument("--search", metavar="POSITION", help="Search and evaluate jobs for a position")
    parser.add_argument("--mock-eval", action="store_true", help="Skip LLM evaluation and use mock data")
    parser.add_argument("--promote", action="store_true", help="Source contacts for jobs ready to proceed")
    parser.add_argument("--reassess", metavar="JOB_ID", type=int, help="Re-run Resume Matcher on a single job")
    parser.add_argument("--reassess-all", action="store_true", help="Re-run Resume Matcher on all active jobs")
    parser.add_argument("--sites", help="Comma-separated list of job sites (unused, reserved for future use)")
    args = parser.parse_args()

    if args.search:
        asyncio.run(run_search(args.search, mock_eval=args.mock_eval))
    elif args.promote:
        asyncio.run(run_promote())
    elif args.reassess is not None or args.reassess_all:
        asyncio.run(run_reassess(job_id=args.reassess, reassess_all=args.reassess_all))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
