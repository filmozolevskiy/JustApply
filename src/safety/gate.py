"""Database Safety Gate — shared detection and decision logic.

This is the single source of truth for what counts as a **Destructive Database
Operation**. The Cursor, Claude Code, and Gemini CLI hook adapters all call
into ``evaluate`` so detection logic cannot drift between runtimes.

Detection is by *path and intent*, not by an allowlist of known-bad commands:
we flag what an action *touches* (the ``data/`` directory, any ``.db`` file,
the out-of-tree backup root) combined with a destructive *verb* (delete,
overwrite, drop, unscoped update, reseed/reset). Routine application writes
(status moves, enrichment, scoped updates) are deliberately not flagged.

Stdlib-only on purpose: a hook subprocess imports this module and must not be
able to fail because some heavy application dependency is missing.
"""

import os
import re
from dataclasses import dataclass

# Environment escape hatch. When set to one of these values the gate steps
# aside (used for a deliberate, human-initiated destructive operation).
_BYPASS_ENV = "JUSTAPPLY_DB_GATE"
_BYPASS_VALUES = {"off", "0", "false", "disabled", "allow", "bypass"}


@dataclass
class Verdict:
    destructive: bool
    category: str = ""
    reason: str = ""
    matched: str = ""


def is_bypassed() -> bool:
    return os.environ.get(_BYPASS_ENV, "").strip().lower() in _BYPASS_VALUES


# --- "What does this action touch?" -----------------------------------------
# A protected target is the data/ directory, any sqlite database file, the
# canonical db filename, or the out-of-tree backup root in $HOME.
_PROTECTED = re.compile(
    r"(?i)(?:^|[\s'\"=(:|&>/~])"
    r"(?:"
    r"\.{0,2}/?data(?:/|\b)"          # data/ directory (incl ./data, ../data)
    r"|just_apply\.(?:db|sqlite|sqlite3)\b"  # canonical db file (NOT just_apply.py etc.)
    r"|\.just_apply\b"                 # ~/.just_apply backup root
    r"|[^\s'\"|;&><]*\.(?:db|sqlite|sqlite3)\b"  # any *.db / *.sqlite path
    r")"
)

# --- "Is the verb destructive?" ---------------------------------------------
_FILE_DELETE = re.compile(r"(?i)\b(rm|rmdir|unlink|shred|srm|trash|trash-put)\b")
_FILE_MOVE_OVERWRITE = re.compile(r"(?i)\b(mv|cp|dd|rsync|install|ln)\b")
_TRUNCATE = re.compile(r"(?i)\btruncate\b")
_FIND_DELETE = re.compile(r"(?i)\bfind\b.*\B-delete\b")
_REDIRECT_OVERWRITE = re.compile(r"(?<!>)>(?!>)\s*[^\s|;&]*\.(?:db|sqlite|sqlite3)\b")
_GIT_DESTRUCTIVE = re.compile(
    r"(?i)\bgit\s+(?:clean\b|checkout\b|restore\b|(?:reset\s+--hard))"
)

# Destructive SQL keywords. DROP/DELETE/TRUNCATE are inherently destructive.
_SQL_HARD = re.compile(
    r"(?i)\b(?:drop\s+(?:table|index|view|database|trigger)|delete\s+from|truncate\s+table)\b"
)
_SQL_UPDATE = re.compile(r"(?i)\bupdate\b[\s\S]*\bset\b")
_SQL_WHERE = re.compile(r"(?i)\bwhere\b")
_SQL_CONTEXT = re.compile(r"(?i)(sqlite3?\b|\.db\b|\.sqlite3?\b|\bjobs\b|just_apply)")

# Reseed / reset of an existing database.
_RESEED = re.compile(
    r"(?i)(?:_seed_db\b|\bseed_db\b|seed\.py\b|src\.db\.seed\b"
    r"|\breseed\w*|\breset[-_]?db\b|\breset[-_]?database\b|\bwipe[-_]?db\b"
    r"|--reseed\b|--reset-db\b|--wipe\b)"
)

# git clean removes untracked files — including the gitignored data/ directory
# — regardless of any explicit path argument, so it is always destructive.
_GIT_CLEAN = re.compile(r"(?i)\bgit\s+clean\b")


def _mentions_protected(text: str) -> bool:
    return bool(_PROTECTED.search(text))


def evaluate(command: str = "", paths=None, cwd: str = "") -> Verdict:
    """Decide whether an intended action is a Destructive Database Operation.

    ``command`` is a shell command string (may be empty for tool-based file
    deletes). ``paths`` is a list of file paths a non-shell tool intends to
    delete or overwrite (e.g. the Cursor ``Delete`` tool target).
    """
    paths = [p for p in (paths or []) if p]
    blob_parts = []
    if command:
        blob_parts.append(command)
    blob_parts.extend(paths)
    blob = "\n".join(blob_parts)

    if not blob.strip():
        return Verdict(False)

    # Non-shell file operations: a tool deletes/overwrites a protected path.
    for p in paths:
        if _mentions_protected(p):
            return Verdict(
                True,
                "file",
                f"Deletes or overwrites a protected database path: {p}",
                p,
            )

    # 1. Reseed / reset of an existing database.
    m = _RESEED.search(blob)
    if m:
        return Verdict(True, "reseed", "Reseed/reset of an existing database", m.group(0))

    # 2. Destructive SQL.
    m = _SQL_HARD.search(blob)
    if m and _SQL_CONTEXT.search(blob):
        return Verdict(True, "sql", f"Destructive SQL: {m.group(0)}", m.group(0))
    if _SQL_UPDATE.search(blob) and not _SQL_WHERE.search(blob) and _SQL_CONTEXT.search(blob):
        return Verdict(True, "sql", "Unscoped UPDATE (no WHERE clause)", "UPDATE ... SET")

    # 3. git clean wipes untracked files (the data/ dir is gitignored).
    if _GIT_CLEAN.search(blob):
        return Verdict(True, "file", "git clean removes untracked files including data/", "git clean")

    # 4. File-level destruction / overwrite of a protected target.
    if not _mentions_protected(blob):
        return Verdict(False)

    if _FILE_DELETE.search(blob):
        return Verdict(True, "file", "Deletes a protected database path", "rm/unlink")
    if _TRUNCATE.search(blob):
        return Verdict(True, "file", "Truncates a protected database path", "truncate")
    if _FIND_DELETE.search(blob):
        return Verdict(True, "file", "find -delete over a protected path", "find -delete")
    if _REDIRECT_OVERWRITE.search(blob):
        return Verdict(True, "file", "Overwrites a database file via redirection", ">")
    if _GIT_DESTRUCTIVE.search(blob):
        return Verdict(True, "file", "git command that can discard protected files", "git")
    if _FILE_MOVE_OVERWRITE.search(blob):
        return Verdict(True, "file", "Moves/overwrites a protected database path", "mv/cp/dd")

    return Verdict(False)
