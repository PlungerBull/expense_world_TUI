"""The running app's log file: one place, rotating, never the token.

`configure()` runs once per launch (the app and `expense import sheet`, from
`__main__.py`); library code only calls `logging.getLogger(__name__)`. What goes in
and what never does: docs/runtime.md "The log".
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER = "expense"
DEFAULT_LOG_PATH = "~/Library/Logs/expense_world/tui.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def log_path() -> Path:
    return Path(os.environ.get("EXPENSE_LOG", DEFAULT_LOG_PATH)).expanduser()


class _SilentRotatingFileHandler(RotatingFileHandler):
    """A failed write is dropped: the default prints to stderr, over the running TUI."""

    def handleError(self, record: logging.LogRecord) -> None:
        pass


def configure() -> None:
    """Send the `expense` loggers to the log file. A location that cannot be created
    or written leaves the app running without a log. Safe to call again: it replaces
    the handler it installed before."""
    logger = logging.getLogger(ROOT_LOGGER)
    for old in [h for h in logger.handlers if isinstance(h, _SilentRotatingFileHandler)]:
        logger.removeHandler(old)
        old.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = _SilentRotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
