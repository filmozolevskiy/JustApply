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


def test_migration_failure_recovery_documents_restore_steps() -> None:
    """Failed upgrades restore from Database Snapshot files, not in-DB Job Backup."""
    text = CONTEXT_PATH.read_text(encoding="utf-8")
    assert "**Migration Failure Recovery**:" in text
    assert "data/just_apply.db" in text
    assert "~/.just_apply/backups/" in text
    assert "no in-database backup table" in text.lower() or "no in-database backup" in text.lower()
    assert "user_version" in text or "versioned migration" in text.lower()


def test_claude_md_links_migration_failure_recovery() -> None:
    """Agent rules point maintainers at CONTEXT.md recovery steps."""
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Migration Failure Recovery" in text
    assert "CONTEXT.md" in text
