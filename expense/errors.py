from functools import wraps
from typing import Any

import typer

from expense.jsonout import json_text


class EngineError(Exception):
    """An engine error envelope `{ error: { code, message, fields, reasons } }`.

    `fields` maps each refused field to its message; `reasons` maps the same keys to
    the engine's reason code (contract: "Error reasons"). Both are `None` when the
    engine sends null. `raw_body` is the response body as sent, for `--json`.
    """

    def __init__(
        self,
        code: str,
        message: str,
        fields: dict[str, Any] | None,
        status: int,
        raw_body: dict[str, Any],
        reasons: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields
        self.reasons = reasons
        self.status = status
        self.raw_body = raw_body


class EngineConnectionError(Exception):
    def __init__(self, url: str, original: Exception):
        super().__init__(str(original))
        self.url = url
        self.original = original


class ConfigMissingError(Exception):
    pass


class ConfigInvalidError(Exception):
    pass


def reason_on(err: EngineError, field: str) -> str | None:
    """The engine's reason code for `field`, or None when it names no reason there.

    Hints switch on this, never on `message` or the `fields` texts, which are for
    people and may be reworded (contract: "Error reasons").
    """
    if not isinstance(err.reasons, dict):
        return None
    return err.reasons.get(field)


def has_reason(err: EngineError, *codes: str) -> bool:
    """True when any field of `err` carries one of `codes` (contract: "Error reasons")."""
    if not isinstance(err.reasons, dict):
        return False
    return any(code in codes for code in err.reasons.values())


# The engine's code for a user whose settings do not exist yet (contract: "Error codes").
# Both rate reads list it among the codes they can return
# (contract: GET /v1/exchange-rates) (contract: GET /v1/exchange-rates/history).
SETTINGS_MISSING = "SETTINGS_MISSING"


def refuses_every_write(err: Exception) -> bool:
    """True for a refusal about the account, not about the request that drew it.

    `SETTINGS_MISSING` holds until first-time setup runs, so every further write
    of the same run would be refused for the same reason. A run of several writes
    stops on it and reports it once. Matched on the error code alone.
    """
    return isinstance(err, EngineError) and err.code == SETTINGS_MISSING


def engine_words(err: EngineError) -> str:
    """The engine's own answer: `CODE — message`, then one line per refused field.

    `format_error` adds its hints under this; the setup screen shows a refused
    key in these words alone, its own line under them saying what to do.
    """
    lines = [f"{err.code} — {err.message}"]
    if err.fields:
        for field, message in err.fields.items():
            lines.append(f"  {field}: {message}")
    return "\n".join(lines)


def format_error(err: Exception) -> str:
    """Human-readable error text, without the leading 'Error: ' prefix.

    Shared by render()'s human branch (CLI) and the TUI toasts/banners, so a hint
    added here reaches every command and screen. Hints switch on the status or the
    error code, never on `message` or the `fields` texts.
    """
    if isinstance(err, EngineError):
        lines = [engine_words(err)]
        if err.status == 401:
            lines.append("")
            lines.append(
                "Hint: the key is missing or not valid. Set a fresh one on "
                "System ▸ Config (press t)."
            )
        if err.code == SETTINGS_MISSING:
            lines.append("")
            lines.append(
                "Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b."
            )
        return "\n".join(lines)
    if isinstance(err, EngineConnectionError):
        return f"could not reach engine at {err.url} (is it running?)"
    # ConfigMissing/ConfigInvalid render as their message, same as any other
    # exception — one fallback covers both.
    return str(err)


# The shared-envelope error families: {ExcType: (envelope code, exit code)}.
# EngineError stays a dedicated branch in render() — its --json output is the
# engine's raw body passed through verbatim, not a client-composed envelope.
_ENVELOPE_ERRORS: dict[type[Exception], tuple[str, int]] = {
    EngineConnectionError: ("CONNECTION_ERROR", 6),
    ConfigMissingError: ("CONFIG_MISSING", 3),
    ConfigInvalidError: ("CONFIG_INVALID", 3),
}

# Everything handle_errors catches — registering a type in _ENVELOPE_ERRORS
# is the single step that makes it render cleanly.
_HANDLED_ERRORS: tuple[type[Exception], ...] = (EngineError, *_ENVELOPE_ERRORS)


def render(err: Exception, *, json_mode: bool) -> tuple[str, int, bool]:
    """Render an error.

    Returns (output_text, exit_code, use_stderr).
    JSON mode writes to stdout so output is pipe-friendly; human mode writes to stderr.
    """
    if isinstance(err, EngineError):
        if json_mode:
            return json_text(err.raw_body), 1, False
        return "Error: " + format_error(err), 1, True

    for exc_type, (code, exit_code) in _ENVELOPE_ERRORS.items():
        if isinstance(err, exc_type):
            if json_mode:
                envelope = {
                    "error": {"code": code, "message": str(err), "fields": None, "reasons": None}
                }
                return json_text(envelope), exit_code, False
            return "Error: " + format_error(err), exit_code, True

    raise err


def handle_errors(fn):
    """Wrap a Typer command so engine/connection/config errors exit cleanly."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        json_mode = bool(kwargs.get("json_output", False))
        try:
            return fn(*args, **kwargs)
        except _HANDLED_ERRORS as err:
            output, exit_code, use_stderr = render(err, json_mode=json_mode)
            typer.echo(output, err=use_stderr)
            raise typer.Exit(code=exit_code) from err

    return wrapper
