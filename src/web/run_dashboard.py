import os
import sys
import uvicorn

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    log_path = os.path.join(project_root, "data", "uvicorn.log")
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
    uvicorn.run("src.web.server:app", host="127.0.0.1", port=8000, reload=True, log_config=log_config)
