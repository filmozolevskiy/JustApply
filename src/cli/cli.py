import asyncio
import sys
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from .. import db as database
from ..core.evaluation_lock import EvaluationLockError
from ..service import (
    RateLimitError,
    backfill_unevaluated_jobs,
    collect_batch_evaluation_results,
    promote_sourced_jobs,
    reassess_all_jobs,
    reassess_job,
    search_jobs,
)


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
    except EvaluationLockError as e:
        print(f"Error: {e}", file=sys.stderr)
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


async def run_backfill(wait: bool = False) -> dict:
    """Submit Batch Evaluation Jobs for unevaluated jobs; poller writes results back."""
    print("Starting backfill evaluation pipeline...")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    try:
        result = await backfill_unevaluated_jobs(
            allowed_remote_types=["remote"],
            wait=wait,
            log_func=log_sync,
        )
    except EvaluationLockError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Backfill complete. "
        f"Total: {result['total']} | Jobs submitted: {result['jobs_submitted']} | "
        f"Batches submitted: {result['batches_submitted']}"
    )
    return result


async def run_collect(wait: bool = False) -> dict:
    """Poll in-flight Batch Evaluation Jobs and write back completed results."""
    print("Collecting batch evaluation results...")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    result = await collect_batch_evaluation_results(wait=wait, log_func=log_sync)

    print(
        f"Collect complete. "
        f"Batches polled: {result['batches_polled']} | "
        f"Matched: {result['matched']} | Rejected: {result['rejected']} | "
        f"Failed: {result['failed']} | Unclassified: {result['unclassified']} | "
        f"In-flight remaining: {result['in_flight_remaining']}"
    )
    return result


async def run_promote() -> list:
    """Run Enrichment on Matched and Accepted jobs: source contacts and generate outreach templates."""
    print("Starting Enrichment pipeline...")

    def log_sync(msg: str, level: str = "info"):
        print(f"  [{level.upper()}] {msg}", file=sys.stderr)

    promoted = await promote_sourced_jobs(log_func=log_sync)

    print(f"Enrichment complete. Processed {len(promoted)} Accepted Job(s).")
    return promoted


def _snapshot_before(reason: str) -> None:
    """Take an out-of-tree Database Snapshot before a major CLI run.

    Best-effort: a snapshot failure must not block the run. See
    docs/adr/0009-database-safety-gate.md.
    """
    try:
        from ..safety import create_snapshot

        path = create_snapshot(reason=reason)
        if path:
            print(f"[INFO] Database snapshot saved to {path}", file=sys.stderr)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="JustApply CLI")
    parser.add_argument("--search", metavar="POSITION", help="Search and evaluate jobs for a position")
    parser.add_argument("--mock-eval", action="store_true", help="Skip LLM evaluation and use mock data")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Run Enrichment on Matched and Accepted jobs (contact sourcing, classification, outreach templates)",
    )
    parser.add_argument("--reassess", metavar="JOB_ID", type=int, help="Re-run Resume Matcher on a single job")
    parser.add_argument("--reassess-all", action="store_true", help="Re-run Resume Matcher on all active jobs")
    parser.add_argument("--backfill", action="store_true", help="Submit batch evaluation for un-evaluated jobs")
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Poll in-flight batch jobs once and write back completed results",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="With --backfill or --collect, wait until all batches finish",
    )
    parser.add_argument("--sites", help="Comma-separated list of job sites (unused, reserved for future use)")
    args = parser.parse_args()

    if args.search:
        _snapshot_before("search")
        asyncio.run(run_search(args.search, mock_eval=args.mock_eval))
    elif args.promote:
        _snapshot_before("promote")
        asyncio.run(run_promote())
    elif args.backfill:
        _snapshot_before("backfill")
        asyncio.run(run_backfill(wait=args.wait))
    elif args.collect:
        asyncio.run(run_collect(wait=args.wait))
    elif args.reassess is not None or args.reassess_all:
        asyncio.run(run_reassess(job_id=args.reassess, reassess_all=args.reassess_all))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
