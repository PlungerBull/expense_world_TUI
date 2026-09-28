import json

import pytest
import typer

from expense.errors import (
    _ENVELOPE_ERRORS,
    ConfigInvalidError,
    ConfigMissingError,
    EngineConnectionError,
    EngineError,
    format_error,
    handle_errors,
    has_reason,
    reason_on,
    render,
)
from tests.unit.helpers import error_body


def _engine_error(message, fields=None, reasons=None):
    return EngineError(
        code="VALIDATION_ERROR",
        message=message,
        fields=fields,
        status=422,
        raw_body={},
        reasons=reasons,
    )


def test_reason_on_reads_the_fields_reason():
    err = _engine_error(
        "Request validation failed.",
        fields={"date_end": "Must not be before date_start."},
        reasons={"date_end": "RANGE_INVERTED"},
    )
    assert reason_on(err, "date_end") == "RANGE_INVERTED"
    assert reason_on(err, "date_start") is None


def test_reason_on_is_none_without_reasons():
    gone = EngineError(code="NOT_FOUND", message="gone", fields=None, status=404, raw_body={})
    assert reason_on(gone, "date_end") is None


def test_has_reason_matches_any_field():
    err = _engine_error(
        "Request validation failed.",
        fields={"title": "Locked.", "amount_cents": "Locked."},
        reasons={"title": "LOCKED", "amount_cents": "LOCKED"},
    )
    assert has_reason(err, "SEALED_PERIOD", "LOCKED")
    assert not has_reason(err, "SEALED_PERIOD")


def test_has_reason_ignores_wording():
    """The words alone decide nothing (contract: "Error reasons")."""
    err = _engine_error(
        "Locked while reconciliation is completed.",
        fields={"amount_cents": "Locked while reconciliation is completed."},
    )
    assert not has_reason(err, "LOCKED")


def test_engine_error_attributes():
    err = EngineError(
        code="VALIDATION_ERROR",
        message="Amount must not be zero",
        fields={"amount_cents": "Must not be zero"},
        status=422,
        raw_body=error_body(
            "VALIDATION_ERROR", "...", {"amount_cents": "..."}, {"amount_cents": "ZERO_AMOUNT"}
        ),
        reasons={"amount_cents": "ZERO_AMOUNT"},
    )
    assert err.code == "VALIDATION_ERROR"
    assert err.status == 422
    assert err.fields == {"amount_cents": "Must not be zero"}


def test_render_engine_error_human_with_fields():
    err = EngineError(
        code="VALIDATION_ERROR",
        message="Amount must not be zero",
        fields={"amount_cents": "Must not be zero"},
        status=422,
        raw_body={},
        reasons={"amount_cents": "ZERO_AMOUNT"},
    )
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 1
    assert use_stderr is True
    assert "Error: VALIDATION_ERROR — Amount must not be zero" in output
    assert "  amount_cents: Must not be zero" in output


def test_render_engine_error_human_401_surfaces_config_set_hint():
    err = EngineError(
        code="UNAUTHORIZED",
        message="Missing or invalid token",
        fields=None,
        status=401,
        raw_body={},
    )
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 1
    assert use_stderr is True
    assert output.startswith("Error: UNAUTHORIZED — Missing or invalid token")
    assert "expense config set --token" in output
    assert "expense auth bootstrap" in output


def test_render_engine_error_human_non_401_no_hint():
    err = EngineError(
        code="NOT_FOUND",
        message="Not found",
        fields=None,
        status=404,
        raw_body={},
    )
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 1
    assert output == "Error: NOT_FOUND — Not found"


def test_render_engine_error_json_passes_through_raw_body():
    raw = error_body("NOT_FOUND", "x", None)
    err = EngineError(
        code="NOT_FOUND",
        message="x",
        fields=None,
        status=404,
        raw_body=raw,
    )
    output, exit_code, use_stderr = render(err, json_mode=True)
    assert exit_code == 1
    assert use_stderr is False
    assert json.loads(output) == raw


def test_render_connection_error_human_includes_url():
    err = EngineConnectionError(
        url="https://nonexistent.invalid",
        original=ConnectionRefusedError("refused"),
    )
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 6
    assert use_stderr is True
    assert "https://nonexistent.invalid" in output
    assert "could not reach engine" in output


def test_render_connection_error_json_envelope():
    err = EngineConnectionError(
        url="https://x.invalid",
        original=TimeoutError("timeout"),
    )
    output, exit_code, _ = render(err, json_mode=True)
    assert exit_code == 6
    envelope = json.loads(output)
    assert envelope["error"]["code"] == "CONNECTION_ERROR"
    assert envelope["error"]["fields"] is None
    assert envelope["error"]["reasons"] is None


def test_render_config_missing_human():
    err = ConfigMissingError("No config found. Run: expense config set ...")
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 3
    assert use_stderr is True
    assert "Error:" in output
    assert "config set" in output


def test_render_config_invalid_json_envelope():
    err = ConfigInvalidError("Config file at /x is not valid JSON.")
    output, exit_code, _ = render(err, json_mode=True)
    assert exit_code == 3
    envelope = json.loads(output)
    assert envelope["error"]["code"] == "CONFIG_INVALID"
    assert envelope["error"]["fields"] is None
    assert envelope["error"]["reasons"] is None


def test_envelope_error_families_are_exactly_connection_and_config():
    """The handled families after the cache deletion — no CACHE_UNAVAILABLE (4),
    no SYNC_CONTRACT (5); those exit codes no longer exist."""
    assert _ENVELOPE_ERRORS == {
        EngineConnectionError: ("CONNECTION_ERROR", 6),
        ConfigMissingError: ("CONFIG_MISSING", 3),
        ConfigInvalidError: ("CONFIG_INVALID", 3),
    }


def test_format_error_engine_error_with_fields():
    err = EngineError(
        code="VALIDATION_ERROR",
        message="Amount must not be zero",
        fields={"amount_cents": "Must not be zero"},
        status=422,
        raw_body={},
        reasons={"amount_cents": "ZERO_AMOUNT"},
    )
    output = format_error(err)
    assert not output.startswith("Error:")
    assert output.startswith("VALIDATION_ERROR — Amount must not be zero")
    assert "  amount_cents: Must not be zero" in output


def test_format_error_leaves_reasons_off_screen():
    """Reason codes are for deciding, not for showing: an error that carries
    them reads exactly like the same error without them."""
    kwargs = dict(
        code="VALIDATION_ERROR",
        message="Amount must not be zero",
        fields={"amount_cents": "Must not be zero"},
        status=422,
        raw_body={},
    )
    with_reasons = EngineError(**kwargs, reasons={"amount_cents": "ZERO_AMOUNT"})
    without = EngineError(**kwargs)

    assert with_reasons.reasons == {"amount_cents": "ZERO_AMOUNT"}
    assert without.reasons is None
    assert format_error(with_reasons) == format_error(without)
    assert format_error(with_reasons) == (
        "VALIDATION_ERROR — Amount must not be zero\n  amount_cents: Must not be zero"
    )
    assert render(with_reasons, json_mode=False) == render(without, json_mode=False)


def test_render_engine_error_json_keeps_the_reasons():
    raw = error_body(
        "VALIDATION_ERROR", "bad", {"amount_cents": "zero"}, {"amount_cents": "ZERO_AMOUNT"}
    )
    err = EngineError(
        code="VALIDATION_ERROR",
        message="bad",
        fields={"amount_cents": "zero"},
        status=422,
        raw_body=raw,
        reasons={"amount_cents": "ZERO_AMOUNT"},
    )
    output, _, _ = render(err, json_mode=True)
    assert json.loads(output) == raw
    assert json.loads(output)["error"]["reasons"] == {"amount_cents": "ZERO_AMOUNT"}


def test_format_error_401_includes_hint():
    err = EngineError(
        code="UNAUTHORIZED",
        message="Missing or invalid token",
        fields=None,
        status=401,
        raw_body={},
    )
    output = format_error(err)
    assert "\n\nHint: token is missing or invalid" in output
    assert "expense config set --token" in output


def test_format_error_connection_error():
    err = EngineConnectionError(
        url="https://nonexistent.invalid",
        original=ConnectionRefusedError("refused"),
    )
    assert format_error(err) == (
        "could not reach engine at https://nonexistent.invalid (is it running?)"
    )


def test_format_error_falls_back_to_str():
    assert format_error(RuntimeError("boom")) == "boom"


@pytest.mark.parametrize(
    "err",
    [
        EngineError(
            code="UNAUTHORIZED",
            message="Missing or invalid token",
            fields={"token": "expired"},
            status=401,
            raw_body={},
        ),
        EngineConnectionError(url="https://x.invalid", original=TimeoutError("timeout")),
        ConfigMissingError("No config found. Run: expense config set ..."),
    ],
)
def test_render_human_is_prefix_plus_format_error(err):
    output, _, _ = render(err, json_mode=False)
    assert output == "Error: " + format_error(err)


def test_render_unknown_exception_reraises():
    with pytest.raises(RuntimeError, match="unexpected"):
        render(RuntimeError("unexpected"), json_mode=False)


def test_handle_errors_catches_engine_error():
    @handle_errors
    def cmd(json_output: bool = False):
        raise EngineError(code="NOT_FOUND", message="x", fields=None, status=404, raw_body={})

    with pytest.raises(typer.Exit) as exc:
        cmd()
    assert exc.value.exit_code == 1


def test_handle_errors_catches_connection_error():
    @handle_errors
    def cmd(json_output: bool = False):
        raise EngineConnectionError(url="https://x", original=Exception("x"))

    with pytest.raises(typer.Exit) as exc:
        cmd()
    assert exc.value.exit_code == 6


def test_handle_errors_catches_config_missing():
    @handle_errors
    def cmd(json_output: bool = False):
        raise ConfigMissingError("no config")

    with pytest.raises(typer.Exit) as exc:
        cmd()
    assert exc.value.exit_code == 3


def test_handle_errors_catches_config_invalid():
    @handle_errors
    def cmd(json_output: bool = False):
        raise ConfigInvalidError("bad config")

    with pytest.raises(typer.Exit) as exc:
        cmd()
    assert exc.value.exit_code == 3


def test_handle_errors_propagates_unexpected():
    @handle_errors
    def cmd(json_output: bool = False):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        cmd()
