import os
import time


class RateLimitError(Exception):
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"Rate limit active. Please wait {wait_seconds} seconds.")


class RateLimiter:
    def __init__(self, lock_file: str, window_seconds: int = 60):
        self._lock_file = lock_file
        self._window = window_seconds

    def acquire(self) -> None:
        current = time.time()
        if os.path.exists(self._lock_file):
            try:
                with open(self._lock_file) as f:
                    last = float(f.read().strip())
                elapsed = current - last
                if elapsed < self._window:
                    raise RateLimitError(int(self._window - elapsed))
            except (ValueError, OSError):
                pass
        try:
            with open(self._lock_file, "w") as f:
                f.write(str(current))
        except OSError:
            pass


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_FILE = os.path.join(_PROJECT_ROOT, "data", ".last_trigger")
scrape_limiter = RateLimiter(LOCK_FILE)
