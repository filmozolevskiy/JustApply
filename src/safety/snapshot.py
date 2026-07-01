"""Out-of-tree Database Snapshots for the Database Safety Gate.

A snapshot is a timestamped, consistent copy of the entire Job Tracker
Database written *outside* the repository (``~/.just_apply/backups/``) so it
survives ``rm -rf data/`` or deletion of the repo clone itself. Snapshots are
taken before a Destructive Database Operation and at the start of major CLI
runs. See ``docs/adr/0009-database-safety-gate.md``.

This module intentionally depends only on the standard library so it can be
imported from a hook subprocess without dragging in the rest of the app.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# Repo root is three levels up from this file: src/safety/snapshot.py -> repo/
_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH = _REPO_ROOT / "data" / "just_apply.db"
BACKUP_DIR = Path.home() / ".just_apply" / "backups"

# Number of most-recent snapshots to retain; older ones are pruned.
RETAIN = 15

_SNAPSHOT_PREFIX = "just_apply"


def _sanitize_reason(reason: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in (reason or "").strip())
    return cleaned.strip("-")[:40]


def create_snapshot(db_path=None, reason: str = "") -> Path | None:
    """Write a consistent copy of ``db_path`` to the out-of-tree backup dir.

    Returns the snapshot path, or ``None`` if there was no database to copy.
    Uses ``VACUUM INTO`` so the copy is transactionally consistent even while
    the database is in use. Never raises on a best-effort copy failure — the
    caller (a safety gate) must not crash because a backup could not be made.
    """
    src = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not src.exists() or src.stat().st_size == 0:
        return None

    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        suffix = _sanitize_reason(reason)
        name = f"{_SNAPSHOT_PREFIX}_{timestamp}"
        if suffix:
            name += f"_{suffix}"
        dest = BACKUP_DIR / f"{name}.db"

        conn = sqlite3.connect(str(src))
        try:
            # VACUUM INTO requires the destination not to exist. Inline the
            # path (no bind params allowed) and escape embedded quotes.
            escaped = str(dest).replace("'", "''")
            conn.execute(f"VACUUM INTO '{escaped}'")
        finally:
            conn.close()

        _prune()
        return dest
    except Exception:
        return None


def _prune(retain: int = None) -> None:
    if retain is None:
        retain = RETAIN
    try:
        snapshots = sorted(
            BACKUP_DIR.glob(f"{_SNAPSHOT_PREFIX}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in snapshots[retain:]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        pass


def latest_snapshot() -> Path | None:
    try:
        snapshots = sorted(
            BACKUP_DIR.glob(f"{_SNAPSHOT_PREFIX}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return snapshots[0] if snapshots else None
    except Exception:
        return None
