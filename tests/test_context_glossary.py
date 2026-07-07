"""Domain glossary hygiene — CONTEXT.md matches implemented schema."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = REPO_ROOT / "CONTEXT.md"


def test_context_does_not_document_jobs_backup_table() -> None:
    """Job Backup was never implemented; glossary must not imply jobs_backup exists."""
    text = CONTEXT_PATH.read_text(encoding="utf-8")
    assert "**Job Backup**:" not in text
    # jobs_backup may appear only as an avoid-term, not as an implemented table.
    for line in text.splitlines():
        if "jobs_backup" in line:
            assert line.strip().startswith("_Avoid_:"), (
                f"jobs_backup must not document an implemented table: {line!r}"
            )


def test_database_snapshot_is_documented_as_recovery_path() -> None:
    """External snapshots under ~/.just_apply/backups/ are the disaster-recovery story."""
    text = CONTEXT_PATH.read_text(encoding="utf-8")
    assert "**Database Snapshot**:" in text
    assert "~/.just_apply/backups/" in text
    assert "VACUUM INTO" in text
