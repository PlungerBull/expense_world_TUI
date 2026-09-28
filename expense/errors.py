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


def error_haystack(err: EngineError) -> str:
    """Lowercased message + string field values, for keyword hint-scanning.

    Shared by the 422-message scans in transactions_cmd and reconcile_cmd, which
    match different keywords against the same haystack.
    """
    haystack = (err.message or "").lower()
    if isinstance(err.fields, dict):
        haystack += (
            " " + " ".join(f"{k} {v}" for k, v in err.fields.items() if isinstance(v, str)).lower()
        )
    return haystack


def format_error(err: Exception) -> str:
    """Human-readable error text, without the leading 'Error: ' prefix.

    Shared by render()'s human branch (CLI) and the TUI toasts/banners.
    """
    if isinstance(err, EngineError):
        lines = [f"{err.code} — {err.message}"]
        if err.fields:
            for field, message in err.fields.items():
                lines.append(f"  {field}: {message}")
        if err.status == 401:
            lines.append("")
            lines.append(
                "Hint: token is missing or invalid. Run "
                "'expense config set --token <pat>' to install a fresh PAT, "
                "or 'expense auth bootstrap' if your account is not yet provisioned."
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
                envelope = {"error": {"code": code, "message": str(err), "fields": None}}
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
