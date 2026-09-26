import json
from datetime import date, datetime
from uuid import UUID

import httpx
import respx
from typer.testing import CliRunner

from expense.commands import _resource, log_cmd
from expense.commands.log_cmd import log as log_impl
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app, whole

cli_app = make_cli_app(commands={"log": log_impl})

runner = CliRunner()


TRANSACTION_RESPONSE = {
    "id": "55555555-5555-5555-5555-555555555555",
    "user_id": "u_123",
    "title": "coffee",
    "amount_cents": 500,
    "date": "2026-04-24T12:00:00Z",
    "account_id": "acct-id",
    "category_id": "cat-id",
    "description": None,
    "transaction_type": 1,
    "hashtag_ids": [],
    "reconciliation_id": None,
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:00Z",
    "version": 1,
    "deleted_at": None,
}


@respx.mock
def test_log_happy(configured):
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "log",
            "--title",
            "coffee",
            "--amount",
            "-500",
            "--account-id",
            "acct-id",
            "--category-id",
            "cat-id",
            "--date",
            "2026-04-24T12:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created:" in result.output

    body = json.loads(route.calls.last.request.content)
    assert body["title"] == "coffee"
    assert body["amount_cents"] == -500
    assert body["account_id"] == "acct-id"
    assert body["category_id"] == "cat-id"
    assert body["date"] == "2026-04-24T12:00:00Z"
    UUID(body["id"])


@respx.mock
def test_log_json_mode(configured):
    respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "log",
            "--title",
            "coffee",
            "--amount",
            "-500",
            "--account-id",
            "a",
            "--category-id",
            "c",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == TRANSACTION_RESPONSE
    assert "Created:" not in result.output


@respx.mock
def test_log_default_date_is_today(configured, monkeypatch):
    # Freeze the CLI's clock so the sent date and the compared date are the same
    # instant — recomputing "today" at assert time could straddle midnight and
    # flake (backlog §5). Patch the seam the default flows through (log_cmd.py:88).
    frozen = "2026-04-24T09:30:00-05:00"
    monkeypatch.setattr(log_cmd, "now_local_iso", lambda: frozen)
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["log", "--title", "coffee", "--amount", "-500", "--account-id", "a", "--category-id", "c"],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(route.calls.last.request.content)
    assert body["date"] == frozen  # the default is now_local_iso(), used verbatim
    parsed = datetime.fromisoformat(body["date"])
    assert parsed.tzinfo is not None


@respx.mock
def test_log_signed_negative_amount(configured):
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    runner.invoke(
        cli_app,
        ["log", "--title", "x", "--amount", "-2000", "--account-id", "a", "--category-id", "c"],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["amount_cents"] == -2000


@respx.mock
def test_log_signed_positive_amount(configured):
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    runner.invoke(
        cli_app,
        ["log", "--title", "x", "--amount", "5000", "--account-id", "a", "--category-id", "c"],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["amount_cents"] == 5000


@respx.mock
def test_log_422_settings_missing_prints_hint(configured):
    respx.post(f"{BASE}/v1/transactions").mock(
        return_value=error_response(
            422,
            "SETTINGS_MISSING",
            "User settings missing.",
            {"user_settings": "Must be provisioned via bootstrap."},
        )
    )
    result = runner.invoke(
        cli_app,
        ["log", "--title", "x", "--amount", "-100", "--account-id", "a", "--category-id", "c"],
    )
    assert result.exit_code == 1
    assert "expense auth bootstrap" in result.output
    assert "SETTINGS_MISSING" in result.output


# ---------------------------------------------------------------------------
# The line form — quick-add phase 2 (2026-08-25)
# ---------------------------------------------------------------------------
# `expense log "tottus -38.60 $signature @korakuen hoy"`. Three behaviours are
# specific to it and each has a test below: a line missing an amount or an
# account, ambiguous, using an unknown tag, or dated ahead is REFUSED (exit 1,
# nothing written — the Inbox that used to take it went 2026-09-12), it always
# asks before writing, and --dry-run shows the parse without touching the
# network. A missing title or category is fine: the engine stores the one as
# null and files the other under @Pendiente.

ACCOUNTS = [
    {"id": "acct-pen", "name": "BCP Signature PEN", "currency_code": "PEN"},
    {"id": "acct-usd", "name": "BCP Signature USD", "currency_code": "USD"},
    {"id": "acct-old", "name": "Retired Card", "currency_code": "PEN", "is_archived": True},
]
CATEGORIES = [
    {"id": "cat-kor", "name": "KORAKUEN"},
    {"id": "cat-tra", "name": "TRANSPORTE"},
    {"id": "cat-sys", "name": "Opening", "is_system": True},
]
HASHTAGS = [{"id": "tag-caja", "name": "CAJA CHICA"}, {"id": "tag-taxi", "name": "TAXI"}]

TODAY = date(2026, 8, 25)


def _refs() -> None:
    """Mock the three reference-list reads every parse needs."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json=whole(ACCOUNTS)))
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=whole(CATEGORIES))
    )
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=httpx.Response(200, json=whole(HASHTAGS)))


def _run(monkeypatch, args, *, tty: bool = True, **kwargs):
    """Invoke with a frozen `today` and, by default, a TTY.

    `require_yes` makes --yes mandatory off a TTY, so a CliRunner would never
    reach the prompt without this. Pass `tty=False` to test that rule itself.
    """
    monkeypatch.setattr(log_cmd, "today_local", lambda: TODAY)
    monkeypatch.setattr(_resource, "stdin_is_tty", lambda: tty)
    return runner.invoke(cli_app, args, **kwargs)


@respx.mock
def test_line_complete_goes_to_the_ledger(configured, monkeypatch):
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(
        monkeypatch,
        ["log", "tottus porongoche -38.60 $signature pen @korakuen #caja 18/8/26"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["title"] == "tottus porongoche"
    assert body["amount_cents"] == -3860
    assert body["account_id"] == "acct-pen"
    assert body["category_id"] == "cat-kor"
    assert body["hashtag_ids"] == ["tag-caja"]
    assert body["date"].startswith("2026-08-18T00:00:00")
    assert "Created:" in result.output


@respx.mock
def test_line_echoes_the_resolved_date_in_words(configured, monkeypatch):
    """Two-digit years are only safe because the resolved date is spelled out."""
    _refs()
    respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(
        monkeypatch,
        ["log", "tottus -38.60 $signature pen @korakuen 18/8/26"],
        input="y\n",
    )

    assert "Tue 18 Aug 2026" in result.output
    assert "BCP Signature PEN" in result.output
    assert "-38.60 PEN" in result.output


@respx.mock
def test_line_declined_writes_nothing(configured, monkeypatch):
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(
        monkeypatch,
        ["log", "tottus -38.60 $signature pen @korakuen hoy"],
        input="n\n",
    )

    assert result.exit_code == 1
    assert not route.called
    assert "Nothing written." in result.output


@respx.mock
def test_line_yes_skips_the_prompt(configured, monkeypatch):
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen hoy", "--yes"])

    assert result.exit_code == 0, result.output
    assert route.called
    assert "Log this to the ledger?" not in result.output


@respx.mock
def test_line_without_an_account_is_refused(configured, monkeypatch):
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "apparka mall -3.50 @transporte #taxi", "--yes"])

    assert result.exit_code == 1, result.output
    assert not ledger.called
    assert "not logged" in result.output
    assert "the line names no account" in result.output


@respx.mock
def test_line_without_a_category_lands_in_the_ledger_under_pendiente(configured, monkeypatch):
    """No category is not a reason (2026-09-12): the body omits it — never
    null — and the echo already says where the engine will file the row."""
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "apparka mall -3.50 $bcp signature pen #taxi", "--yes"])

    assert result.exit_code == 0, result.output
    body = json.loads(ledger.calls.last.request.content)
    assert "category_id" not in body
    assert body["title"] == "apparka mall"
    assert body["hashtag_ids"] == ["tag-taxi"]
    assert "PENDIENTE" in result.output.upper()
    assert "Created:" in result.output


@respx.mock
def test_line_without_a_title_sends_none_and_echoes_a_dash(configured, monkeypatch):
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    # `--` keeps typer from reading the leading minus as an option; a shell
    # user quotes the line, which is the same thing.
    result = _run(monkeypatch, ["log", "--yes", "--", "-6.60 $bcp signature pen"])

    assert result.exit_code == 0, result.output
    body = json.loads(ledger.calls.last.request.content)
    assert "title" not in body
    assert "  —" in result.output


@respx.mock
def test_ambiguous_name_is_refused_and_lists_the_candidates(configured, monkeypatch):
    """An ambiguous name counts as no name (decided 2026-08-25) — and the way
    out is to retype it, so the candidates are printed with the refusal."""
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature @korakuen hoy", "--yes"])

    assert result.exit_code == 1, result.output
    assert not ledger.called
    assert "BCP Signature PEN" in result.output
    assert "BCP Signature USD" in result.output
    assert "matches 2 accounts" in result.output


@respx.mock
def test_unmatched_hashtag_is_refused_and_never_created(configured, monkeypatch):
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen #nope hoy", "--yes"])

    assert result.exit_code == 1, result.output
    assert not ledger.called
    assert "matches no hashtags" in result.output


@respx.mock
def test_complete_but_dated_ahead_is_refused(configured, monkeypatch):
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "alquiler -1800 $signature pen @korakuen manana", "--yes"])

    assert result.exit_code == 1, result.output
    assert not ledger.called
    assert "dated ahead" in result.output


@respx.mock
def test_flag_form_needs_only_amount_and_account(configured):
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(cli_app, ["log", "--amount", "-660", "--account-id", "acct-id"])

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert "title" not in body and "category_id" not in body
    assert body["amount_cents"] == -660


@respx.mock
def test_line_without_a_date_defaults_to_now(configured, monkeypatch):
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    frozen = "2026-08-25T14:31:07-05:00"
    monkeypatch.setattr(log_cmd, "now_local_iso", lambda: frozen)
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen", "--yes"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content)["date"] == frozen


@respx.mock
def test_dry_run_touches_no_write_endpoint(configured, monkeypatch):
    _refs()
    ledger = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen hoy", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not ledger.called
    assert "Nothing written (--dry-run)." in result.output


@respx.mock
def test_dry_run_json_is_the_parse(configured, monkeypatch):
    _refs()
    result = _run(
        monkeypatch,
        ["log", "tottus -38.60 $signature @korakuen 18/8/26", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["target"] == "refused"
    assert body["reasons"] == ['"$signature" matches 2 accounts']
    assert body["parsed"]["date"] == "2026-08-18"
    assert body["parsed"]["date_given"] is True
    assert body["parsed"]["missing"] == ["account"]
    assert body["parsed"]["unresolved"][0]["kind"] == "account"
    assert len(body["parsed"]["unresolved"][0]["candidates"]) == 2
    assert body["parsed"]["spans"]  # a span per token, for a colouring caller
    assert body["payload"] == {}  # a refused line has no body


@respx.mock
def test_json_without_yes_is_refused(configured, monkeypatch):
    """A y/N prompt would land in the middle of the JSON."""
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen hoy", "--json"])

    assert result.exit_code == 1
    assert not route.called
    assert "--json cannot prompt" in result.output


@respx.mock
def test_json_with_yes_stays_a_clean_engine_body(configured, monkeypatch):
    _refs()
    respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(
        monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen hoy", "--yes", "--json"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == TRANSACTION_RESPONSE


# --- the two forms never mix ------------------------------------------------


def test_line_and_flag_together_is_refused(configured):
    result = runner.invoke(cli_app, ["log", "tottus -38.60", "--title", "x"])
    assert result.exit_code == 1
    assert "two different forms" in result.output


def test_bare_log_names_both_forms(configured):
    result = runner.invoke(cli_app, ["log"])
    assert result.exit_code == 1
    assert "--amount" in result.output and "--account-id" in result.output
    assert "expense log" in result.output


def test_flag_form_missing_a_required_flag_says_which(configured):
    """Only `--amount` and `--account-id` are required (2026-09-12); a missing
    `--category-id` is not a complaint any more."""
    result = runner.invoke(cli_app, ["log", "--title", "x", "--amount", "-100"])
    assert result.exit_code == 1
    assert "--account-id" in result.output
    assert "--category-id" not in result.output


def test_dry_run_needs_a_line(configured):
    result = runner.invoke(
        cli_app,
        [
            "log",
            "--title",
            "x",
            "--amount",
            "-1",
            "--account-id",
            "a",
            "--category-id",
            "c",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "--dry-run needs a line" in result.output


def test_empty_line_is_refused(configured):
    result = runner.invoke(cli_app, ["log", "   "])
    assert result.exit_code == 1
    assert "the line is empty" in result.output


@respx.mock
def test_line_off_a_tty_demands_yes(configured, monkeypatch):
    """Piped or scripted, there is nobody to answer — the same rule every
    other confirmed write in the CLI follows (`require_yes`)."""
    _refs()
    route = respx.post(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(201, json=TRANSACTION_RESPONSE)
    )
    result = _run(monkeypatch, ["log", "tottus -38.60 $signature pen @korakuen hoy"], tty=False)

    assert result.exit_code == 1
    assert not route.called
    assert "--yes is required" in result.output
