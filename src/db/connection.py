import os
import sqlite3

from .migrations import apply_pipeline_status_backfill, apply_rejected_at_backfill, run_migrations
from .seed import _seed_db

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "just_apply.db")

# Milliseconds to wait on locked tables before raising OperationalError.
# WAL + timeout reduce contention when the Kanban Dashboard and Batch Poller
# read while CLI enrichment writes overlap on the same local database file.
_BUSY_TIMEOUT_MS = 5000


def get_db_connection(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    return conn


def _seeding_allowed(db_existed, allow_seed):
    """Auto-seeding is only safe for a genuinely new database file.

    Seeding an *existing* but emptied database silently overwrites real data
    with fake rows — the one Destructive Database Operation no shell hook can
    observe (it happens in-process). Restrict auto-seed to brand-new files;
    seeding an existing/emptied db requires an explicit opt-in. See
    docs/adr/0009-database-safety-gate.md.
    """
    if allow_seed:
        return True
    if os.environ.get("JUSTAPPLY_ALLOW_SEED", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return not db_existed


def init_db(db_path=None, allow_seed=False):
    if db_path is None:
        db_path = DB_PATH
    db_existed = os.path.exists(os.path.abspath(db_path))
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = get_db_connection(db_path)
    run_migrations(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    count = cursor.fetchone()[0]
    if count == 0 and _seeding_allowed(db_existed, allow_seed):
        _seed_db(cursor)
        conn.commit()

    apply_pipeline_status_backfill(conn)
    apply_rejected_at_backfill(conn)

    from .contacted_elsewhere import ensure_contacted_profiles_index

    ensure_contacted_profiles_index(conn)

    conn.close()
