"""The running app's log file: one place, rotating, never the token.

`configure()` runs once per launch (the app and `expense import sheet`, from
`__main__.py`); library code only calls `logging.getLogger(__name__)`. What goes in
and what never does: docs/runtime.md "The log".
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER = "expense"
DEFAULT_LOG_PATH = "~/Library/Logs/expense_world/tui.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


_MARK = "[REDACTED]"
# A `Bearer ...` value, or anything shaped like a token (the `ewe_pat_` prefix).
_SECRET = re.compile(r"Bearer\s+\S+|ewe_pat_\S+")
# Every token a client has sent, so one saved while the app runs is covered too.
_tokens: set[str] = set()


def remember_token(token: str) -> None:
    """Blank this token (and its stripped form) in every record from now on."""
    _tokens.update({token, token.strip()} - {""})


def redact(text: str) -> str:
    for token in sorted(_tokens, key=len, reverse=True):
        text = text.replace(token, _MARK)
    return _SECRET.sub(_MARK, text)


class _TokenFilter(logging.Filter):
    """Blank the token and any `Bearer ...` value in the whole record, traceback
    included, whatever a message or an exception's text happens to carry."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = None
            if record.exc_info:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = redact(record.exc_text)
        except Exception:  # noqa: BLE001 - a log call never raises into app code
            pass
        return True


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
    handler.addFilter(_TokenFilter())
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
