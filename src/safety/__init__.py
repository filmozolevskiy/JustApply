"""Database Safety Gate package.

See ``docs/adr/0009-database-safety-gate.md`` and the ``Database Safety Gate``
entry in ``CONTEXT.md`` for the full design.
"""

from .gate import Verdict, evaluate, is_bypassed
from .snapshot import BACKUP_DIR, create_snapshot, latest_snapshot

__all__ = [
    "Verdict",
    "evaluate",
    "is_bypassed",
    "BACKUP_DIR",
    "create_snapshot",
    "latest_snapshot",
]
