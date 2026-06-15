import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from .. import db as database
from ..service import RateLimitError, promote_sourced_jobs, search_jobs


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
            active_resume=_resume_name_for_position(position),
            mock_eval=mock_eval,
            allowed_remote_types=allowed_remote_types,
            log_func=log_sync,
        )
    except RateLimitError as e:
        print(f"Warning: Rate limit active. Please wait {e.wait_seconds} seconds.", file=sys.stderr)
        sys.exit(1)

    print(f"Search complete. {len(saved)} jobs saved to database.")
    return saved


async def run_promote() -> list:
    """Enrich jobs ready for outreach: source contacts and generate messages."""
    print("Starting promote pipeline...")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    promoted = await promote_sourced_jobs(log_func=log_sync)

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
