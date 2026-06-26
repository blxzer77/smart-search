import sys
from typing import Callable

ProgressReporter = Callable[[str], None] | None


def make_progress_reporter(enabled: bool) -> ProgressReporter:
    if not enabled:
        return None

    def emit(message: str) -> None:
        sys.stderr.write(f"[research] {message}\n")
        sys.stderr.flush()

    return emit
