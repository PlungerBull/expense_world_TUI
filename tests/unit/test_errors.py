import json

import pytest
import typer

from expense.errors import (
    _ENVELOPE_ERRORS,
    ConfigInvalidError,
    ConfigMissingError,
    EngineConnectionError,
    EngineError,
    app_lines,
    engine_text,
    engine_words,
    format_error,
    handle_errors,
    key_index,
    refuses_every_write,
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


def test_render_engine_error_human_is_the_engine_words_alone():
    """The sheet import prints what the engine said and nothing of the app's:
    no screen to open, no key to press, no typed command."""
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
    assert output == "Error: UNAUTHORIZED — Missing or invalid token"


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
    err = ConfigMissingError("No config found. Open the app.")
    output, exit_code, use_stderr = render(err, json_mode=False)
    assert exit_code == 3
    assert use_stderr is True
    assert "Error:" in output
    assert "Open the app" in output


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
    assert "\n\nHint: the key is missing or not valid" in output
    assert "System ▸ Config (press t)" in output


SETTINGS_HINT = "Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b."


def _settings_missing(message, fields, reasons=None, raw_body=None):
    return EngineError(
        code="SETTINGS_MISSING",
        message=message,
        fields=fields,
        status=422,
        raw_body=raw_body or {},
        reasons=reasons,
    )


def test_format_error_settings_missing_includes_the_setup_hint():
    """The first-time-setup hint has one home, so every command and screen shows it
    (contract: "Error codes")."""
    err = _settings_missing(
        "User settings have not been provisioned.",
        {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        {"user_settings": "NOT_PROVISIONED"},
    )
    assert format_error(err) == (
        "SETTINGS_MISSING — User settings have not been provisioned.\n"
        "  user_settings: Must be provisioned via POST /v1/auth/bootstrap.\n"
        "\n" + SETTINGS_HINT
    )
    assert format_error(err).count("Hint:") == 1


@pytest.mark.parametrize(
    ("message", "fields"),
    [
        ("User settings have not been provisioned.", {"user_settings": "Must be provisioned."}),
        ("reworded", {"user_settings": "also reworded"}),
        ("", None),
    ],
)
def test_format_error_settings_hint_follows_the_code_not_the_wording(message, fields):
    assert format_error(_settings_missing(message, fields)).endswith("\n\n" + SETTINGS_HINT)


def test_format_error_other_422_has_no_setup_hint():
    """Another code gets no hint, even carrying the very words of a settings refusal."""
    err = EngineError(
        code="VALIDATION_ERROR",
        message="User settings have not been provisioned.",
        fields={"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        status=422,
        raw_body={},
        reasons={"user_settings": "NOT_PROVISIONED"},
    )
    assert "Hint:" not in format_error(err)
    assert "press b" not in format_error(err)


def test_render_settings_missing_json_is_the_raw_body_without_the_hint():
    raw = error_body(
        "SETTINGS_MISSING",
        "User settings have not been provisioned.",
        {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        {"user_settings": "NOT_PROVISIONED"},
    )
    err = _settings_missing(
        raw["error"]["message"], raw["error"]["fields"], raw["error"]["reasons"], raw
    )
    output, exit_code, use_stderr = render(err, json_mode=True)
    assert json.loads(output) == raw
    assert "Hint" not in output
    assert (exit_code, use_stderr) == (1, False)


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
        ConfigMissingError("No config found. Open the app."),
    ],
)
def test_render_human_is_prefix_plus_engine_text(err):
    output, _, _ = render(err, json_mode=False)
    assert output == "Error: " + engine_text(err)


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


def test_refuses_every_write_holds_for_line_codes_exhausted_under_any_key():
    """Every line code given: no create that needs a new line can land again
    (contract: "Transactions (Ledger)", "Bank lines")."""
    for key in ("id", "transaction_id", "transactions.3.id", "rows.0.id"):
        assert refuses_every_write(
            EngineError(
                "LIMIT_REACHED",
                "No codes.",
                {key: "x"},
                422,
                {},
                reasons={key: "LINE_CODES_EXHAUSTED"},
            )
        )
    # a create cap is about one resource, not every write
    assert not refuses_every_write(
        EngineError("LIMIT_REACHED", "Cap.", {"id": "x"}, 422, {}, reasons={"id": "CAP_REACHED"})
    )
    # the reason under another code is not it
    assert not refuses_every_write(
        EngineError(
            "VALIDATION_ERROR", "x", {"id": "x"}, 422, {}, reasons={"id": "LINE_CODES_EXHAUSTED"}
        )
    )


def test_refuses_every_write_follows_the_code_alone():
    assert refuses_every_write(_settings_missing("reworded", None))
    assert not refuses_every_write(
        EngineError(
            code="VALIDATION_ERROR",
            message="User settings have not been provisioned.",
            fields={"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
            status=422,
            raw_body={},
            reasons={"user_settings": "NOT_PROVISIONED"},
        )
    )
    assert not refuses_every_write(EngineError("UNAUTHORIZED", "no", None, 401, {}))
    assert not refuses_every_write(EngineConnectionError("http://x", RuntimeError("down")))


# ---------------------------------------------------------------------------
# What to do next: chosen by the engine's code and reason
# ---------------------------------------------------------------------------
# Every refusal with code CONFLICT, FORBIDDEN or LIMIT_REACHED names the rule
# that fired in `reasons`, keyed by the thing refused
# (contract: "Base Conventions", "`fields` and `reasons` semantics"); so does the
# VALIDATION_ERROR an opening balance draws when asked to move
# (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put"). The words
# in these tests are stand-ins: the line follows the reason, never them.


def _refusal(code: str, key: str, reason: str, status: int = 409, message: str = "stand-in"):
    return EngineError(
        code=code,
        message=message,
        fields={key: "stand-in field words"},
        status=status,
        raw_body={},
        reasons={key: reason},
    )


APP_FAULT = (
    "Not your mistake: the app sent it wrong and nothing was saved. "
    "Try again; if it happens again, report it."
)


@pytest.mark.parametrize(
    ("code", "key", "reason", "on_list", "line"),
    [
        # 1 · the approved delete lines, word for word
        (
            "CONFLICT",
            "account_id",
            "HAS_TRANSACTIONS",
            True,
            "To retire it instead, archive it: press a.",
        ),
        (
            "CONFLICT",
            "category_id",
            "HAS_TRANSACTIONS",
            True,
            "Move its transactions to another category first.",
        ),
        (
            "FORBIDDEN",
            "category_id",
            "SYSTEM_CATEGORY",
            True,
            "System categories cannot be renamed or deleted.",
        ),
        # pending-hashtag-manage 4 B, both refusals, and 5 B
        (
            "FORBIDDEN",
            "hashtag_id",
            "SYSTEM_HASHTAG",
            True,
            "The pending hashtag cannot be renamed or deleted.",
        ),
        (
            "VALIDATION_ERROR",
            "name",
            "RESERVED_NAME",
            False,
            "That name belongs to a system row: pick another.",
        ),
        (
            "VALIDATION_ERROR",
            "name",
            "SYSTEM_NAME_FIXED",
            False,
            "Built-in names never change: press esc to leave it as it is.",
        ),
        # pending-hashtag-manage 7 B: the ledger's bulk h, on a transaction write's key
        (
            "VALIDATION_ERROR",
            "hashtag_ids",
            "OPENING_BALANCE_NOT_TAGGED",
            False,
            "Leave the opening balance out of the selection.",
        ),
        # the Edit form's whole-line write refusing a part's `parts.<i>.hashtag_ids` with
        # OPENING_BALANCE_NOT_TAGGED: the engine's words alone, with no line of the app's
        ("VALIDATION_ERROR", "parts.0.hashtag_ids", "OPENING_BALANCE_NOT_TAGGED", False, None),
        ("VALIDATION_ERROR", "parts.2.hashtag_ids", "OPENING_BALANCE_NOT_TAGGED", True, None),
        # a transaction in a completed reconciliation: the engine's words alone
        ("CONFLICT", "transaction_id", "IN_COMPLETED_RECONCILIATION", True, None),
        # archived-account 3 A: the engine's words alone, on every route that answers it
        ("CONFLICT", "transaction_id", "ACCOUNT_ARCHIVED", True, None),
        ("CONFLICT", "reconciliation_id", "ACCOUNT_ARCHIVED", False, None),
        ("VALIDATION_ERROR", "amount_cents", "ACCOUNT_ARCHIVED", False, None),
        ("VALIDATION_ERROR", "ending_balance_cents", "ACCOUNT_ARCHIVED", True, None),
        # `t` on an account already of that kind, or archived: the engine's words alone
        ("CONFLICT", "account_id", "KIND_UNCHANGED", True, None),
        ("CONFLICT", "account_id", "ACCOUNT_ARCHIVED", True, None),
        # person-reconciliations 1 A: a reconciliation stops `t`, with the line on
        # how; a new reconciliation on a person keeps the engine's words alone
        (
            "CONFLICT",
            "account_id",
            "HAS_RECONCILIATION",
            True,
            "On Reconciliations, press d on each of its reconciliations; "
            "a completed one needs u first.",
        ),
        ("VALIDATION_ERROR", "account_id", "PERSON_ACCOUNT", False, None),
        # 2
        ("CONFLICT", "name", "NAME_EXISTS", False, "That name is taken: pick another."),
        # a statement code another account in this currency has gets the app's line;
        # a code clashing with a reconciliation, a person given a code and a code
        # that is not three capital letters keep the engine's words alone
        (
            "CONFLICT",
            "statement_code",
            "STATEMENT_CODE_EXISTS",
            False,
            "Another account in this currency has this code: "
            "pick another, or clear it there first.",
        ),
        ("VALIDATION_ERROR", "statement_code", "STATEMENT_MONTH_TAKEN", False, None),
        ("VALIDATION_ERROR", "statement_code", "COMPLETED_STATEMENT_JOINED", False, None),
        ("VALIDATION_ERROR", "statement_code", "PERSON_ACCOUNT", False, None),
        ("VALIDATION_ERROR", "statement_code", "INVALID_FORMAT", False, None),
        # 3A
        ("LIMIT_REACHED", "id", "CAP_REACHED", False, "Delete one first."),
        # 4, on a form and in a batch or an import
        (
            "CONFLICT",
            "operation_code",
            "OPERATION_CODE_EXISTS",
            False,
            "That account already has a row with this operation number: "
            "look there for a duplicate.",
        ),
        (
            "CONFLICT",
            "rows.3.operation_code",
            "OPERATION_CODE_EXISTS",
            False,
            "That account already has a row with this operation number: "
            "look there for a duplicate.",
        ),
        # 5A: the key for the screen you are on
        (
            "CONFLICT",
            "hashtag_id",
            "CONCURRENT_CHANGE",
            True,
            "It changed at the same moment: press r, then try again.",
        ),
        (
            "CONFLICT",
            "category_id",
            "CONCURRENT_CHANGE",
            False,
            "It changed at the same moment: save again.",
        ),
        # 6B
        (
            "CONFLICT",
            "category_id",
            "RESERVED_NAME_HELD",
            False,
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
        # a user hashtag holds the pending hashtag's name: the engine's message
        # names the remedy, so the category line stays off
        ("CONFLICT", "hashtag_ids", "RESERVED_NAME_HELD", False, None),
        ("CONFLICT", "hashtag_id", "RESERVED_NAME_HELD", True, None),
        (
            "CONFLICT",
            "hashtag_ids",
            "CONCURRENT_CHANGE",
            False,
            "It changed at the same moment: save again.",
        ),
        # the pending hashtag beside another, a hashtag deleted meanwhile: no line
        ("VALIDATION_ERROR", "hashtag_ids", "PENDING_HASHTAG_NOT_ALONE", False, None),
        ("VALIDATION_ERROR", "transactions.0.hashtag_ids", "INVALID_REFERENCE", False, None),
        # 7
        (
            "CONFLICT",
            "account_id",
            "OPENING_BALANCE_EXISTS",
            False,
            "It got one meanwhile: close the form and open it again to change it.",
        ),
        # 8B
        (
            "CONFLICT",
            "reconciliation_id",
            "RECONCILIATION_NOT_DRAFT",
            True,
            "Press u to revert it, then d again.",
        ),
        # 9A, both cases
        ("CONFLICT", "id", "ID_EXISTS", False, APP_FAULT),
        ("CONFLICT", "transactions.0.id", "ID_EXISTS", False, APP_FAULT),
        ("CONFLICT", "X-Idempotency-Key", "IDEMPOTENCY_KEY_REUSED", False, APP_FAULT),
        # never met by the app: not wired
        ("CONFLICT", "X-Idempotency-Key", "SECRET_NOT_REPLAYABLE", False, None),
        # opening-balance rows 2B, on a list (bulk b / c) and on the Edit form
        (
            "VALIDATION_ERROR",
            "account_id",
            "OPENING_BALANCE_ACCOUNT_FIXED",
            False,
            "To move an opening balance, set it on the other account's Edit form.",
        ),
        (
            "VALIDATION_ERROR",
            "category_id",
            "OPENING_BALANCE_CATEGORY_FIXED",
            False,
            "An opening balance always stays in @Opening.",
        ),
        # the field lock answers first in a completed reconciliation: no line
        ("VALIDATION_ERROR", "account_id", "LOCKED", False, None),
    ],
)
def test_each_reason_gets_exactly_its_picked_line(code, key, reason, on_list, line):
    """The engine's words, a blank line, then the line drawn for that reason."""
    from expense.errors import next_step

    status = {"FORBIDDEN": 403, "VALIDATION_ERROR": 422}.get(code, 409)
    err = _refusal(code, key, reason, status=status)
    assert next_step(err, on_list=on_list) == line
    words = f"{code} — stand-in\n  {key}: stand-in field words"
    expected = words if line is None else f"{words}\n\n{line}"
    assert format_error(err, on_list=on_list) == expected


def test_the_line_follows_the_reason_never_the_status_or_the_words():
    """The same reason under another status, or the words of one refusal under
    another reason, change nothing; no reason means no line."""
    from expense.errors import next_step

    taken = _refusal("CONFLICT", "name", "NAME_EXISTS", status=418, message="whatever")
    assert next_step(taken) == "That name is taken: pick another."
    worded = _refusal(
        "CONFLICT", "account_id", "CONCURRENT_CHANGE", message="Account has active transactions."
    )
    assert next_step(worded) == "It changed at the same moment: save again."
    bare = EngineError("CONFLICT", "Account has active transactions.", None, 409, {})
    assert next_step(bare) is None
    assert format_error(bare) == "CONFLICT — Account has active transactions."
    # another code carrying a refusal's reason gets no line, either way round
    assert next_step(_refusal("VALIDATION_ERROR", "name", "NAME_EXISTS", status=422)) is None
    assert next_step(_refusal("CONFLICT", "account_id", "OPENING_BALANCE_ACCOUNT_FIXED")) is None
    # a validation error with null reasons has no line
    assert next_step(EngineError("VALIDATION_ERROR", "bad", {"x": "y"}, 422, {})) is None
    assert next_step(RuntimeError("boom")) is None


def test_the_table_is_keyed_by_code_and_reason_only():
    """Guard: the one table of next steps holds (code, reason) pairs, with codes
    the engine sends a reason on every key for, and reasons in the engine's
    SHOUTY_SNAKE form — never a route, a status or a sentence. The one other
    code is `VALIDATION_ERROR`, for the three opening-balance reasons, the
    missing ending balance and the two name rules of the built-in rows alone."""
    import re

    from expense.errors import NEXT_STEPS, REFUSAL_CODES, NextStep

    assert REFUSAL_CODES == {"CONFLICT", "FORBIDDEN", "LIMIT_REACHED"}
    validation_reasons = {
        "OPENING_BALANCE_ACCOUNT_FIXED",
        "OPENING_BALANCE_CATEGORY_FIXED",
        "OPENING_BALANCE_NOT_TAGGED",
        "ENDING_BALANCE_REQUIRED",
        "RESERVED_NAME",
        "SYSTEM_NAME_FIXED",
    }
    for key, step in NEXT_STEPS.items():
        assert isinstance(key, tuple) and len(key) == 2
        code, reason = key
        if code == "VALIDATION_ERROR":
            assert reason in validation_reasons, reason
        else:
            assert code in REFUSAL_CODES
        assert re.fullmatch(r"[A-Z][A-Z_]+", reason), reason
        assert isinstance(step, NextStep)
        for field_key in (*step.by_key, *step.no_line_on):
            assert re.fullmatch(r"[a-z_]+", field_key)
    assert {reason for _code, reason in NEXT_STEPS} == {
        "HAS_TRANSACTIONS",
        "SYSTEM_CATEGORY",
        "SYSTEM_HASHTAG",
        "NAME_EXISTS",
        "STATEMENT_CODE_EXISTS",
        "CAP_REACHED",
        "OPERATION_CODE_EXISTS",
        "CONCURRENT_CHANGE",
        "RESERVED_NAME_HELD",
        "OPENING_BALANCE_EXISTS",
        "HAS_RECONCILIATION",
        "RECONCILIATION_NOT_DRAFT",
        "ID_EXISTS",
        "IDEMPOTENCY_KEY_REUSED",
        "OPENING_BALANCE_ACCOUNT_FIXED",
        "OPENING_BALANCE_CATEGORY_FIXED",
        "OPENING_BALANCE_NOT_TAGGED",
        "ENDING_BALANCE_REQUIRED",
        "RESERVED_NAME",
        "SYSTEM_NAME_FIXED",
    }


def test_a_missing_ending_balance_says_press_c_again():
    """The refused complete keeps the engine's words whole, then the line saying
    what to do (contract: POST /v1/statements/{statement_id}/complete,
    "Every ending balance must be entered"). The message is the practice engine's;
    the contract does not print it."""
    from expense.errors import next_step

    err = _refusal(
        "VALIDATION_ERROR",
        "balances.acc1.ending_balance_cents",
        "ENDING_BALANCE_REQUIRED",
        status=422,
        message="Cannot complete the statement without every account's ending balance.",
    )
    assert next_step(err) == "Press c again: the app asks for it first."
    assert format_error(err).endswith("\n\nPress c again: the app asks for it first.")
    assert format_error(err).startswith(
        "VALIDATION_ERROR — Cannot complete the statement without every account's ending balance."
    )


def test_no_hint_is_chosen_by_status_and_route_anywhere():
    """Guard: the status-and-route table is gone, and no code keys a hint on a
    (collection, status) pair."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "expense"
    pattern = re.compile(r"\(\s*\"[a-z_]+\"\s*,\s*(?:401|403|404|409|422)\s*\)")
    offenders = [
        str(path)
        for path in root.rglob("*.py")
        if "DELETE_REFUSAL_HINTS" in path.read_text(encoding="utf-8")
        or pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders


@pytest.mark.parametrize(
    ("err", "replay"),
    [
        (_refusal("CONFLICT", "transactions.0.id", "ID_EXISTS"), True),
        (_refusal("CONFLICT", "transactions.1.id", "ID_EXISTS"), False),
        (_refusal("CONFLICT", "category_id", "CONCURRENT_CHANGE"), False),
        (_refusal("CONFLICT", "category_id", "RESERVED_NAME_HELD"), False),
        (_refusal("CONFLICT", "transactions.0.id", "IDEMPOTENCY_KEY_REUSED"), False),
        (EngineError("CONFLICT", "id exists", None, 409, {}), False),
        (RuntimeError("boom"), False),
    ],
)
def test_only_its_own_id_taken_is_a_replay(err, replay):
    from expense.errors import is_own_id_replay

    assert is_own_id_replay(err, "transactions.0.id") is replay


def test_a_replay_with_a_second_reason_is_a_refusal():
    """A create sent again answers `ID_EXISTS` alone, before any other refusal
    (contract: "Base Conventions", "Which refusal comes first on a create"), so a
    taken id beside another reason is no replay of the app's own write."""
    from expense.errors import is_own_id_replay

    err = EngineError(
        "CONFLICT",
        "x",
        {"id": "a", "name": "b"},
        409,
        {},
        reasons={"id": "ID_EXISTS", "name": "NAME_EXISTS"},
    )
    assert not is_own_id_replay(err, "id")


@pytest.mark.parametrize(
    ("key", "collection", "field"),
    [
        ("transactions.3.amount_cents", "transactions", "amount_cents"),
        ("rows.0.date", "rows", "date"),
        ("parts.1.hashtag_ids", "parts", "hashtag_ids"),
        ("parts.1", "parts", None),
        ("parts", "parts", None),
        ("parts.x.amount_cents", "parts", None),
        ("rows.3.date", "parts", None),
        ("category_id", "transactions", None),
    ],
)
def test_key_field_reads_the_field_an_item_key_names(key, collection, field):
    from expense.errors import key_field

    assert key_field(key, collection) == field


@pytest.mark.parametrize(
    ("key", "collection", "index"),
    [
        ("parts.0.amount_cents", "parts", 0),
        ("parts.11", "parts", 11),
        ("rows.3.date", "rows", 3),
        ("parts", "parts", None),
        ("parts.x.amount_cents", "parts", None),
        ("rows.3", "parts", None),
        ("transaction_id", "parts", None),
    ],
)
def test_key_index_reads_the_place_a_refused_key_names(key, collection, index):
    """One reader for the bank import's `rows.<i>` and the split's `parts.<i>`."""
    assert key_index(key, collection) == index


@pytest.mark.parametrize(
    ("err", "lines"),
    [
        (EngineError("VALIDATION_ERROR", "Nope.", {"x": "bad"}, 422, {}), []),
        (
            EngineError(
                "CONFLICT",
                "Busy.",
                {"transaction_id": "busy"},
                409,
                {},
                reasons={"transaction_id": "CONCURRENT_CHANGE"},
            ),
            ["It changed at the same moment: save again."],
        ),
        (
            EngineError("UNAUTHORIZED", "No.", None, 401, {}),
            [
                "Hint: the key is missing or not valid. "
                "Set a fresh one on System ▸ Config (press t)."
            ],
        ),
    ],
    ids=["none", "next-step", "401"],
)
def test_app_lines_are_what_format_error_puts_under_the_engine_words(err, lines):
    """`format_error` is the engine's words and each app line after a blank line."""
    assert app_lines(err) == lines
    assert format_error(err) == "\n\n".join([engine_words(err), *lines])
