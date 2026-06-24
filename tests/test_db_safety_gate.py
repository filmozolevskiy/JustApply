import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, get_jobs, add_job
import src.db.connection as _connection
from src.safety import gate, snapshot

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
_GATE_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "hooks", "db_safety_gate.py")


# --- Detection: destructive operations are flagged --------------------------

@pytest.mark.parametrize("command", [
    "rm -rf data",
    "rm -rf data/",
    "rm data/just_apply.db",
    "rm -f ./data/just_apply.db",
    "unlink data/just_apply.db",
    "shred data/just_apply.db",
    "truncate -s 0 data/just_apply.db",
    "mv data/just_apply.db /tmp/old.db",
    "sqlite3 data/just_apply.db 'DROP TABLE jobs'",
    "sqlite3 data/just_apply.db 'DELETE FROM jobs'",
    "sqlite3 data/just_apply.db \"UPDATE jobs SET status='found'\"",
    "python3 -c \"reseed_db()\"",
    "python3 -m src.db.seed",
    "find data -name '*.db' -delete",
    "echo '' > data/just_apply.db",
    "git clean -fdx",
    "rm -rf ~/.just_apply/backups",
])
def test_destructive_commands_flagged(command):
    verdict = gate.evaluate(command=command)
    assert verdict.destructive, f"should flag: {command}"


# --- Detection: routine / unrelated operations pass through -----------------

@pytest.mark.parametrize("command", [
    "python3 -m src.cli --search 'QA'",
    "python3 -m src.cli --promote",
    "sqlite3 data/just_apply.db 'SELECT * FROM jobs'",
    "sqlite3 data/just_apply.db \"UPDATE jobs SET status='found' WHERE id=3\"",
    "pytest tests/",
    "git status",
    "git commit -m 'wip'",
    "rm -rf node_modules",
    "rm -rf build/",
    "ls data/",
    "cat data/just_apply.db | head",
    "sqlite3 data/just_apply.db 'VACUUM INTO \"/tmp/backup.db\"'",
])
def test_benign_commands_pass(command):
    verdict = gate.evaluate(command=command)
    assert not verdict.destructive, f"should not flag: {command}"


def test_unscoped_update_flagged_scoped_passes():
    assert gate.evaluate(command="sqlite3 data/just_apply.db 'UPDATE jobs SET x=1'").destructive
    assert not gate.evaluate(
        command="sqlite3 data/just_apply.db 'UPDATE jobs SET x=1 WHERE id=2'"
    ).destructive


def test_file_path_delete_flagged():
    """A non-shell tool deleting the db path (paths arg) is flagged."""
    assert gate.evaluate(paths=["data/just_apply.db"]).destructive
    assert gate.evaluate(paths=["/abs/path/data/just_apply.db"]).destructive
    assert not gate.evaluate(paths=["src/web/dashboard.html"]).destructive


def test_bypass_env(monkeypatch):
    monkeypatch.setenv("JUSTAPPLY_DB_GATE", "off")
    assert gate.is_bypassed()
    monkeypatch.setenv("JUSTAPPLY_DB_GATE", "")
    assert not gate.is_bypassed()


# --- Snapshots --------------------------------------------------------------

def test_snapshot_creates_out_of_tree_copy(tmp_path, monkeypatch):
    db_path = tmp_path / "live.db"
    init_db(str(db_path))
    backups = tmp_path / "backups"
    monkeypatch.setattr(snapshot, "BACKUP_DIR", backups)

    out = snapshot.create_snapshot(db_path=str(db_path), reason="test")
    assert out is not None
    assert out.exists()
    assert out.parent == backups
    # Snapshot is a usable database with the seeded rows.
    rows = get_jobs(str(out))
    assert len(rows) > 0


def test_snapshot_none_when_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "BACKUP_DIR", tmp_path / "backups")
    assert snapshot.create_snapshot(db_path=str(tmp_path / "missing.db")) is None


def test_snapshot_prune_keeps_latest(tmp_path, monkeypatch):
    db_path = tmp_path / "live.db"
    init_db(str(db_path))
    monkeypatch.setattr(snapshot, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(snapshot, "RETAIN", 3)
    for _ in range(6):
        snapshot.create_snapshot(db_path=str(db_path), reason="loop")
    remaining = list((tmp_path / "backups").glob("just_apply_*.db"))
    assert len(remaining) == 3


# --- In-process reseed guard ------------------------------------------------

def test_new_db_is_seeded(tmp_path):
    db_path = str(tmp_path / "fresh.db")
    init_db(db_path)
    assert len(get_jobs(db_path)) > 0


def test_existing_emptied_db_not_reseeded(tmp_path):
    db_path = str(tmp_path / "live.db")
    init_db(db_path)
    # Simulate data loss: wipe all rows from an existing database file.
    conn = _connection.get_db_connection(db_path)
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    assert len(get_jobs(db_path)) == 0

    # Re-running init_db must NOT silently repopulate with seed data.
    init_db(db_path)
    assert len(get_jobs(db_path)) == 0


def test_existing_emptied_db_reseeds_with_explicit_optin(tmp_path):
    db_path = str(tmp_path / "live.db")
    init_db(db_path)
    conn = _connection.get_db_connection(db_path)
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()

    init_db(db_path, allow_seed=True)
    assert len(get_jobs(db_path)) > 0


def test_existing_emptied_db_reseeds_with_env(tmp_path, monkeypatch):
    db_path = str(tmp_path / "live.db")
    init_db(db_path)
    conn = _connection.get_db_connection(db_path)
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()

    monkeypatch.setenv("JUSTAPPLY_ALLOW_SEED", "1")
    init_db(db_path)
    assert len(get_jobs(db_path)) > 0


def test_existing_db_with_data_untouched(tmp_path):
    """Existing db with real rows keeps them (no seeding, no wipe)."""
    db_path = str(tmp_path / "live.db")
    init_db(db_path)
    conn = _connection.get_db_connection(db_path)
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    real_id = add_job({"title": "Real Job", "company": "RealCo"}, db_path)

    init_db(db_path)
    jobs = get_jobs(db_path)
    assert len(jobs) == 1
    assert jobs[0].id == real_id


# --- Adapter end-to-end (subprocess, real runtime payloads) -----------------

def _run_gate(payload, env_extra=None):
    env = dict(os.environ)
    env.pop("JUSTAPPLY_DB_GATE", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, _GATE_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc


def test_adapter_cursor_blocks_shell_rm():
    payload = {
        "hook_event_name": "beforeShellExecution",
        "command": "rm -rf data/just_apply.db",
        "cwd": ".",
        "cursor_version": "1.7.2",
    }
    proc = _run_gate(payload)
    out = json.loads(proc.stdout)
    assert out["permission"] == "deny"


def test_adapter_cursor_allows_benign_shell():
    payload = {
        "hook_event_name": "beforeShellExecution",
        "command": "python3 -m src.cli --search 'QA'",
        "cwd": ".",
        "cursor_version": "1.7.2",
    }
    proc = _run_gate(payload)
    out = json.loads(proc.stdout)
    assert out["permission"] == "allow"


def test_adapter_cursor_edit_content_not_blocked():
    """Editing a file whose CONTENT mentions data/*.db must not be blocked."""
    payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/repo/src/db/connection.py",
            "contents": "DB_PATH = 'data/just_apply.db'\n# DROP TABLE jobs is mentioned here",
        },
        "cwd": ".",
        "cursor_version": "1.7.2",
    }
    proc = _run_gate(payload)
    out = json.loads(proc.stdout)
    assert out["permission"] == "allow"


def test_adapter_cursor_delete_db_blocked():
    payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "Delete",
        "tool_input": {"path": "data/just_apply.db"},
        "cwd": ".",
        "cursor_version": "1.7.2",
    }
    proc = _run_gate(payload)
    out = json.loads(proc.stdout)
    assert out["permission"] == "deny"


def test_adapter_claude_blocks_with_exit_2():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf data/just_apply.db"},
    }
    proc = _run_gate(payload, env_extra={"CLAUDE_PROJECT_DIR": "/repo"})
    assert proc.returncode == 2
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_adapter_gemini_blocks_with_deny():
    payload = {
        "type": "BeforeTool",
        "toolName": "run_shell_command",
        "toolInput": {"command": "rm -rf data/just_apply.db"},
    }
    proc = _run_gate(payload, env_extra={"GEMINI_SESSION_ID": "abc"})
    out = json.loads(proc.stdout)
    assert out["decision"] == "deny"
    assert proc.returncode == 0


def test_adapter_bypass_env_allows():
    payload = {
        "hook_event_name": "beforeShellExecution",
        "command": "rm -rf data/just_apply.db",
        "cwd": ".",
        "cursor_version": "1.7.2",
    }
    proc = _run_gate(payload, env_extra={"JUSTAPPLY_DB_GATE": "off"})
    out = json.loads(proc.stdout)
    assert out["permission"] == "allow"
