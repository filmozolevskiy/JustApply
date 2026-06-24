import os
import sys
from pathlib import Path

import uvicorn

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # Keep the server log OUT of the watched tree. Writing it under data/ made the
    # reloader fire on the app's own log writes, restarting the server on every
    # request and freezing the UI in a reload storm.
    log_dir = Path.home() / ".just_apply" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / "uvicorn.log")
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": log_path,
                "mode": "a",
            }
        },
        "root": {"level": "INFO", "handlers": ["file"]},
    }
    # Only watch source code. Excluding data/ (the live db + logs) and venv/ stops
    # the reloader from restarting mid-request when the app writes runtime files.
    uvicorn.run(
        "src.web.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[os.path.join(project_root, "src")],
        reload_excludes=["*.db", "*.db-wal", "*.db-shm", "*.log", "data/*"],
        log_config=log_config,
    )
