"""Contract: `POST /transactions/import`.

The TUI import door sends the bank's download whole and draws what comes
back, so what the preview and the apply say is the engine's word. Every file
here is a made-up download built in the test (`workbook`), never a real one:
this repo is public. Each goes out through the app's own body,
`request_body` in expense/bank_import/engine.py, and its answer is read by the
app's own `answer_rows` and `day_mismatches` where a test names them. Pinned here:

  - a dry run answers each row by its spreadsheet row and writes nothing; the
    apply writes what the dry run showed, and the same file again is
    `matched` by `operation_code`, naming that row's bank line, not retitled,
    and with no day whose totals disagree;
  - every row goes to the currency of the account in its own `Moneda`: a card's
    download on an account holding soles and dollars puts each row on its own
    currency, a soles download on that account leaves its dollars untouched
    (their line, balance and day never claimed), and a dollar row sent to an
    account holding no dollars is `CURRENCY_NOT_HELD` on `rows.<row>.account_id`,
    its message naming the row and the currency, nothing written, on the dry run
    and the apply alike (contract: POST /v1/transactions/import, "Accounts");
  - every answer row and every `day_mismatches` entry reads `account_id` and
    `currency_code`;
  - a row of 0 is `skipped`: read, counted, never written;
  - `"true"` and `1` for `dry_run` are `INVALID_FORMAT` on `dry_run`, nothing written;
  - a row dated after today refuses the whole download, dry run and apply alike,
    `FUTURE_DATE` on `rows.<row>.date`, its message naming the row, nothing written;
  - a day where the ledger holds a line the file does not is a
    `day_mismatches` entry per currency: both totals signed, the leftover line as
    exactly `bank_line_id`, its `line_code`, its signed `net_cents` and its `parts`,
    each the response `GET /transactions/{id}` returns;
  - a split line no file row claimed is one entry holding every part, and a
    row found in no line is named by its spreadsheet row;
  - a day whose totals agree is still reported when it holds a line no file
    row claimed;
  - a row not in the ledger, dated inside a completed statement's days, is `sealed` and
    names the statement: never written, never an error;
  - a row matched by `operation_code` on another day moves its line, every
    part, to the bank's day: `redated`, counted in `counts.redated`, said on
    the dry run and done by the apply;
  - a completed statement the line is in stops that move: the row is
    still `matched`, `redate_blocked_by` names the statement, which the app's own
    `statement_names` reads by its id to the name the preview shows, the line keeps
    its day, and the file's other rows are written.

Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from expense.bank_import.engine import answer_rows, day_mismatches
from expense.bank_import.flow import statement_names
from tests.contract.conftest import (
    CARD_HEADER,
    CURRENT_HEADER,
    account_balance,
    assert_refusal,
    download_body,
    live_ids,
    read_signed,
    refused,
    replace_parts,
    send_download,
    transaction_count,
)

TITLE = "DLC*RIDES LIMA PE"


def _code() -> str:
    return f"OP{uuid4().hex[:10]}"


def _day_of(client, zone: ZoneInfo, tx_id: str) -> datetime:
    """A transaction's `date` in `display_timezone`."""
    return datetime.fromisoformat(client.get(f"/transactions/{tx_id}")["date"]).astimezone(zone)


def test_the_apply_writes_what_the_dry_run_showed_and_the_same_file_then_matches(scratch):
    client = scratch.client
    account = scratch.account()
    code, other = _code(), _code()
    rows = [
        CURRENT_HEADER,
        ["05/03/2026", f"  {TITLE}  ", "S/", -25.9, code],
        ["06/03/2026", "PAGO PLANILLA", "S/", 6519, other],
    ]
    dry = send_download(client, account, rows, dry_run=True)
    assert dry["dry_run"] is True
    assert [r["row"] for r in dry["rows"]] == [2, 3]  # the spreadsheet's own numbers
    assert {(r["account_id"], r["currency_code"]) for r in dry["rows"]} == {(account, "PEN")}
    assert [r["outcome"] for r in dry["rows"]] == ["new", "new"]
    first = dry["rows"][0]
    assert (first["account_id"], first["currency_code"]) == (account, "PEN")
    assert (first["date"], first["title"]) == ("2026-03-05", TITLE)
    assert (first["amount_cents"], first["transaction_type"]) == (2590, 1)
    assert (dry["rows"][1]["amount_cents"], dry["rows"][1]["transaction_type"]) == (651900, 2)
    assert first["operation_code"] == code and first["transaction_id"] is None
    assert dry["counts"]["new"] == 2
    assert transaction_count(client, account) == 0

    applied = send_download(client, account, rows, dry_run=False)
    made = scratch.took(applied)
    shown = (
        "row",
        "account_id",
        "currency_code",
        "date",
        "amount_cents",
        "transaction_type",
        "title",
        "outcome",
    )
    assert [{k: r[k] for k in shown} for r in applied["rows"]] == [
        {k: r[k] for k in shown} for r in dry["rows"]
    ]
    assert applied["counts"] == dry["counts"]
    assert len(made) == 2 and transaction_count(client, account) == 2
    written = client.get(f"/transactions/{made[0]}")
    assert (written["operation_code"], written["title"]) == (code, TITLE)
    assert (written["account_id"], written["currency_code"]) == (account, "PEN")

    again = send_download(client, account, rows, dry_run=False)
    only = again["rows"][0]
    assert {(r["account_id"], r["currency_code"]) for r in again["rows"]} == {(account, "PEN")}
    assert only["outcome"] == "matched" and only["rule"] == "operation_code"
    assert only["bank_line_id"] == written["bank_line_id"]
    assert only["retitled"] is False
    assert again["counts"]["retitled"] == 0
    assert again["day_mismatches"] == []
    assert transaction_count(client, account) == 2


def test_a_cards_download_lands_each_row_on_the_currency_of_its_own_moneda(scratch):
    """Sent on the one account holding soles and dollars, a row in `S/` goes to its soles and
    a row in `$` to its dollars (contract: POST /v1/transactions/import, "Accounts"); each
    answer row reads the account and the currency, and so does the app's own reading of it."""
    client = scratch.client
    account = scratch.account("PEN", "USD")
    rows = [
        CARD_HEADER,
        ["2026-03-11", "EDO SUSHI BAR", "S/", -49],
        ["2026-03-09", "APPLE.COM/BILL", "$", -21.17],
        ["2026-03-08", "UBER TRIP", "S/", -4.2],
    ]
    wanted = [(2, "PEN", "new"), (3, "USD", "new"), (4, "PEN", "new")]
    for dry_run in (True, False):
        answer = send_download(client, account, rows, dry_run=dry_run)
        made = scratch.took(answer)  # cleaned up whatever the checks below find
        assert [(r["row"], r["currency_code"], r["outcome"]) for r in answer["rows"]] == wanted
        assert {r["account_id"] for r in answer["rows"]} == {account}
        read = answer_rows(answer)
        assert [(r.row, r.account_id, r.currency_code) for r in read] == [
            (2, account, "PEN"),
            (3, account, "USD"),
            (4, account, "PEN"),
        ]
    landed = [read_signed(client, tx) for tx in made]
    assert sorted((t["account_id"], t["currency_code"], t["amount_cents"]) for t in landed) == (
        sorted([(account, "PEN", -4900), (account, "USD", -2117), (account, "PEN", -420)])
    )
    assert transaction_count(client, account) == 3
    assert account_balance(client, account, "PEN") == -5320
    assert account_balance(client, account, "USD") == -2117


def test_a_soles_download_leaves_the_dollars_of_the_account_untouched(scratch):
    """A download in soles sent to an account holding soles and dollars takes every row in
    soles; a dollar line of the same day and amount is never claimed, its day is not checked
    and its money is as it was (contract: POST /v1/transactions/import, "Accounts")."""
    client = scratch.client
    account = scratch.account("PEN", "USD")
    dollars = scratch.row(account, "2026-03-09", -2590, "USD")["id"]
    before = read_signed(client, dollars)
    balance = account_balance(client, account, "USD")
    rows = [CARD_HEADER, ["2026-03-09", TITLE, "S/", -25.9]]
    for dry_run in (True, False):
        answer = send_download(client, account, rows, dry_run=dry_run)
        made = scratch.took(answer)  # cleaned up whatever the checks below find
        (only,) = answer["rows"]
        # same day and amount as the dollar line, yet not claimed: another currency
        assert (only["account_id"], only["currency_code"], only["outcome"]) == (
            account,
            "PEN",
            "new",
        )
        assert answer["day_mismatches"] == []
        assert read_signed(client, dollars) == before
        assert account_balance(client, account, "USD") == balance
    assert live_ids(client, account) == {dollars, *made}
    assert account_balance(client, account, "PEN") == -2590


def test_a_dollar_row_to_an_account_without_dollars_is_refused_and_nothing_is_written(scratch):
    """The first row in a currency the account holds no live currency in is `422`
    `CURRENCY_NOT_HELD` on `rows.<row>.account_id`, its message naming the row and the
    currency, the download refused whole on the dry run and the apply
    (contract: POST /v1/transactions/import, "Accounts")."""
    client = scratch.client
    account = scratch.account("PEN")
    scratch.row(account, "2026-03-05", -500, "PEN")
    rows = [
        CARD_HEADER,
        ["2026-03-11", "EDO SUSHI BAR", "S/", -49],
        ["2026-03-09", "APPLE.COM/BILL", "$", -21.17],
        ["2026-03-08", "APPLE.COM/MUSIC", "$", -5],
    ]

    def read() -> tuple:
        return (
            client.get("/transactions", params={"account_id": account}),
            client.get(f"/accounts/{account}"),
            transaction_count(client, account),
        )

    before = read()
    for dry_run in (True, False):
        err = refused(lambda dry_run=dry_run: send_download(client, account, rows, dry_run=dry_run))
        assert_refusal(err, 422, "VALIDATION_ERROR", "rows.3.account_id", "CURRENCY_NOT_HELD")
        assert err.fields["rows.3.account_id"] == "Row 3: The account holds no USD."
        assert read() == before


def test_dry_run_is_a_json_boolean_and_nothing_else(scratch):
    """`"true"` and `1` for `dry_run` are `422` `INVALID_FORMAT` on `dry_run` alone and nothing
    is written, while the JSON `true` is the dry run
    (contract: "Base Conventions", "Booleans and whole numbers in a request")
    (contract: POST /v1/transactions/import)."""
    client = scratch.client
    account = scratch.account()
    good = download_body(account, [CARD_HEADER, ["2026-03-10", TITLE, "S/", -25.9]], dry_run=True)
    for value in ("true", 1):
        err = refused(
            lambda v=value: client.post("/transactions/import", json_body={**good, "dry_run": v})
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "dry_run", "INVALID_FORMAT")
        assert transaction_count(client, account) == 0
    assert client.post("/transactions/import", json_body=good)["dry_run"] is True
    assert transaction_count(client, account) == 0


def test_a_row_of_zero_is_skipped_and_never_written(scratch):
    client = scratch.client
    account = scratch.account()
    rows = [
        CARD_HEADER,
        ["2026-03-10", "PAGO TARJETA", "S/", 0],
        ["2026-03-10", TITLE, "S/", -25.9],
    ]
    for dry_run in (True, False):
        answer = send_download(client, account, rows, dry_run=dry_run)
        scratch.took(answer)  # cleaned up whatever the checks below find
        skipped, new = answer["rows"]
        assert {(r["account_id"], r["currency_code"]) for r in answer["rows"]} == {(account, "PEN")}
        assert (skipped["row"], skipped["outcome"]) == (2, "skipped")
        assert (skipped["amount_cents"], skipped["transaction_type"]) == (0, None)
        assert skipped["transaction_id"] is None
        assert new["outcome"] == "new"
        assert (answer["counts"]["skipped"], answer["counts"]["new"]) == (1, 1)
        assert answer["day_mismatches"] == []
    assert transaction_count(client, account) == 1


def test_a_future_dated_row_is_refused_naming_its_row(scratch):
    """A row dated after today is `422` `FUTURE_DATE` on `rows.<row>.date`, the row
    the spreadsheet's own, its message `Row <row>: Must not be in the future.`, and the
    whole download is refused with nothing written, on the dry run and the apply
    (contract: POST /v1/transactions/import, "Rejected up front with `422`")."""
    client = scratch.client
    account = scratch.account()
    rows = [
        CURRENT_HEADER,
        ["05/03/2026", TITLE, "S/", -25.9, _code()],
        ["19/03/2099", "PAGO FUTURO", "S/", -10, _code()],
    ]
    for dry_run in (True, False):
        err = refused(lambda dry_run=dry_run: send_download(client, account, rows, dry_run=dry_run))
        assert_refusal(err, 422, "VALIDATION_ERROR", "rows.3.date", "FUTURE_DATE")
        assert err.fields["rows.3.date"] == "Row 3: Must not be in the future."
    assert transaction_count(client, account) == 0


def test_a_leftover_ledger_line_is_reported_on_its_day_in_its_currency(scratch):
    client = scratch.client
    account = scratch.account("PEN", "USD")
    ledger = [scratch.row(account, "2026-03-09", -2590)["id"] for _ in range(2)]
    dollars = scratch.row(account, "2026-03-09", -1000, "USD")["id"]
    # a card's rows: no operation code, matched by day and total in their own currency
    # the dollar row is first: reported days are grouped by currency in the order of each
    # currency's first file row (contract: POST /v1/transactions/import, "`day_mismatches`"),
    # which is not the order of the codes
    rows = [CARD_HEADER, ["2026-03-09", "APPLE", "$", -21.17], ["2026-03-09", TITLE, "S/", -25.9]]
    body = send_download(client, account, rows, dry_run=True)
    new, soles = body["rows"]
    assert soles["outcome"] == "matched" and soles["rule"] == "same_day"
    assert (new["outcome"], new["currency_code"]) == ("new", "USD")
    assert (soles["account_id"], soles["currency_code"]) == (account, "PEN")
    assert new["account_id"] == account
    dollars_day, soles_day = body["day_mismatches"]
    for day in body["day_mismatches"]:
        assert day["account_id"] == account and day["date"] == "2026-03-09"
    assert soles_day["currency_code"] == "PEN"
    assert (soles_day["file_net_cents"], soles_day["ledger_net_cents"]) == (-2590, -5180)
    assert soles_day["unmatched_rows"] == []
    (line,) = soles_day["unclaimed_lines"]
    assert set(line) == {"bank_line_id", "line_code", "net_cents", "parts"}
    assert line["net_cents"] == -2590
    (part,) = line["parts"]
    assert part["id"] in ledger
    # The part is the transaction response itself: a magnitude, the direction
    # in `transaction_type` (contract: "Base Conventions", "Sign convention — responses").
    assert part == client.get(f"/transactions/{part['id']}")
    assert (part["amount_cents"], part["transaction_type"]) == (2590, 1)
    assert (part["account_id"], part["currency_code"]) == (account, "PEN")
    assert line["bank_line_id"] == part["bank_line_id"]
    assert line["line_code"] == part["line_code"]
    assert soles["bank_line_id"] != line["bank_line_id"]

    assert dollars_day["currency_code"] == "USD"
    assert (dollars_day["file_net_cents"], dollars_day["ledger_net_cents"]) == (-2117, -3117)
    assert dollars_day["unmatched_rows"] == [2]
    (dollar_line,) = dollars_day["unclaimed_lines"]
    (dollar_part,) = dollar_line["parts"]
    assert dollar_part["id"] == dollars and dollar_part["currency_code"] == "USD"

    read = day_mismatches(body, "the account")
    assert [(d.account_id, d.currency_code, d.date_iso) for d in read] == [
        (account, "USD", "2026-03-09"),
        (account, "PEN", "2026-03-09"),
    ]
    assert [d.unmatched_rows for d in read] == [(2,), ()]
    assert [[p["id"] for p in d.unclaimed_parts] for d in read] == [[dollars], [part["id"]]]


def test_a_split_unclaimed_line_is_one_entry_with_every_part(scratch):
    client = scratch.client
    account = scratch.account()
    whole = scratch.row(account, "2026-03-12", -10000)
    parts = replace_parts(client, whole["bank_line_id"], [-6000, -4000], scratch.transactions)

    body = send_download(
        client, account, [CARD_HEADER, ["2026-03-12", TITLE, "S/", -25.9]], dry_run=True
    )
    (only,) = body["rows"]
    assert only["outcome"] == "new"
    (day,) = body["day_mismatches"]
    assert (day["account_id"], day["currency_code"]) == (account, "PEN")
    assert (day["file_net_cents"], day["ledger_net_cents"]) == (-2590, -12590)
    assert day["unmatched_rows"] == [2]  # by its spreadsheet row
    (line,) = day["unclaimed_lines"]
    assert set(line) == {"bank_line_id", "line_code", "net_cents", "parts"}
    assert line["net_cents"] == -10000
    assert {p["id"] for p in line["parts"]} == {p["id"] for p in parts}
    assert {p["bank_line_id"] for p in line["parts"]} == {line["bank_line_id"]}
    assert {p["line_code"] for p in line["parts"]} == {line["line_code"]}
    assert sorted(p["amount_cents"] for p in line["parts"]) == [4000, 6000]


def test_a_day_whose_totals_agree_is_reported_for_its_unclaimed_lines(scratch):
    """A +50 and a -50 the file does not have cancel out, and the day is still
    reported (contract: POST /v1/transactions/import)."""
    client = scratch.client
    account = scratch.account()
    scratch.row(account, "2026-03-13", -2590)
    plus = scratch.row(account, "2026-03-13", 5000)["id"]
    minus = scratch.row(account, "2026-03-13", -5000)["id"]

    body = send_download(
        client, account, [CARD_HEADER, ["2026-03-13", TITLE, "S/", -25.9]], dry_run=True
    )
    (only,) = body["rows"]
    assert only["outcome"] == "matched" and only["rule"] == "same_day"
    assert {(r["account_id"], r["currency_code"]) for r in body["rows"]} == {(account, "PEN")}
    (day,) = body["day_mismatches"]
    assert (day["account_id"], day["currency_code"]) == (account, "PEN")
    assert day["date"] == "2026-03-13"
    assert day["file_net_cents"] == day["ledger_net_cents"] == -2590
    assert day["unmatched_rows"] == []
    lines = day["unclaimed_lines"]
    keys = {"bank_line_id", "line_code", "net_cents", "parts"}
    assert all(set(line) == keys for line in lines)
    assert sorted(line["net_cents"] for line in lines) == [-5000, 5000]
    assert sorted(p["id"] for line in lines for p in line["parts"]) == sorted([plus, minus])


def test_a_row_inside_a_completed_statement_comes_back_sealed(scratch):
    client = scratch.client
    account = scratch.account()
    anchor = scratch.row(account, "2026-02-05", -100)["id"]
    statement = scratch.completed(account, "2026-02-01", "2026-02-28", anchor)

    rows = [CURRENT_HEADER, ["10/02/2026", TITLE, "S/", -25.9, _code()]]
    body = send_download(client, account, rows, dry_run=False)
    (only,) = body["rows"]
    assert only["outcome"] == "sealed"
    assert only["sealed_by"] == statement["id"]
    assert (only["account_id"], only["currency_code"]) == (account, "PEN")
    assert only["transaction_id"] is None
    assert body["counts"]["sealed"] == 1
    assert transaction_count(client, account) == 1  # the anchor only


def test_a_code_matched_line_moves_every_part_to_the_banks_day(scratch):
    client = scratch.client
    zone = scratch.zone
    account = scratch.account()
    code = _code()
    whole = scratch.row(account, "2026-03-03", -2590, operation_code=code)
    parts = replace_parts(client, whole["bank_line_id"], [-1590, -1000], scratch.transactions)

    rows = [CURRENT_HEADER, ["04/03/2026", TITLE, "S/", -25.9, code]]
    dry = send_download(client, account, rows, dry_run=True)
    (only,) = dry["rows"]
    assert only["outcome"] == "matched" and only["rule"] == "operation_code"
    assert {(r["account_id"], r["currency_code"]) for r in dry["rows"]} == {(account, "PEN")}
    assert only["redated"] is True
    assert only["redate_blocked_by"] is None
    assert dry["counts"]["redated"] == 1
    # a moved line counts on the bank's day: nothing disagrees
    assert dry["day_mismatches"] == []
    assert {_day_of(client, zone, p["id"]).date().isoformat() for p in parts} == {"2026-03-03"}

    applied = send_download(client, account, rows, dry_run=False)
    (only,) = applied["rows"]
    assert only["outcome"] == "matched"
    assert {(r["account_id"], r["currency_code"]) for r in applied["rows"]} == {(account, "PEN")}
    assert only["redated"] is True and only["redate_blocked_by"] is None
    assert applied["counts"]["redated"] == 1
    for p in parts:
        moved = _day_of(client, zone, p["id"])
        assert moved.date().isoformat() == "2026-03-04"
        assert (moved.hour, moved.minute) == (0, 0)  # 00:00, as a created row is dated


def test_a_completed_statement_stops_the_move_and_the_rest_imports(scratch, target):
    client = scratch.client
    zone = scratch.zone
    account = scratch.account()
    code = _code()
    closed = scratch.row(account, "2026-02-27", -2590, operation_code=code)["id"]
    statement = scratch.completed(account, "2026-02-01", "2026-02-28", closed)

    rows = [
        CURRENT_HEADER,
        ["02/03/2026", TITLE, "S/", -25.9, code],
        ["03/03/2026", "PAGO", "S/", -10, _code()],
    ]
    for dry_run in (True, False):
        body = send_download(client, account, rows, dry_run=dry_run)
        made = scratch.took(body)  # cleaned up whatever the checks below find
        stopped, new = body["rows"]
        assert {(r["account_id"], r["currency_code"]) for r in body["rows"]} == {(account, "PEN")}
        assert stopped["outcome"] == "matched" and stopped["rule"] == "operation_code"
        assert stopped["redated"] is False
        assert stopped["redate_blocked_by"] == statement["id"]
        # the statement named through the app's own read, as the preview shows it
        # (contract: GET /v1/statements/{statement_id})
        names, failure = statement_names(target, answer_rows(body), verbose=False)
        assert (names, failure) == ({statement["id"]: statement["name"]}, None)
        assert new["outcome"] == "new"
        assert body["counts"]["redated"] == 0
        assert _day_of(client, zone, closed).date().isoformat() == "2026-02-27"
    # the stopped move is not an error: the file's other row is written
    assert len(made) == 1 and transaction_count(client, account) == 2
    assert read_signed(client, made[0])["amount_cents"] == -1000
