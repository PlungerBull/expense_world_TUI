"""Contract: `POST /transactions/import`.

The TUI import door sends the bank's download whole and draws what comes
back, so what the preview and the apply say is the engine's word. Every file
here is a made-up download built in the test (`workbook`), never a real one:
this repo is public. Each goes out through the app's own body,
`request_body` in expense/bank_import/engine.py. Pinned here:

  · a dry run answers each row by its spreadsheet row and writes nothing; the
    apply writes what the dry run showed, and the same file again is
    `matched` by `operation_code`, naming that row's bank line, not retitled,
    and with no day whose totals disagree;
  · a card's download, sent on its soles account, puts its soles rows on the
    soles account and its dollar rows on the dollar account the engine pairs
    with it;
  · a row of 0 is `skipped`: read, counted, never written;
  · a row dated after today refuses the whole download, dry run and apply alike,
    `FUTURE_DATE` on `rows.<row>.date`, its message naming the row, nothing written;
  · a day where the ledger holds a line the file does not is a
    `day_mismatches` entry: both totals signed, the leftover line as exactly
    `bank_line_id`, its `line_code`, its signed `net_cents` and its `parts`,
    each the response `GET /transactions/{id}` returns;
  · a split line no file row claimed is one entry holding every part, and a
    row found in no line is named by its spreadsheet row;
  · a day whose totals agree is still reported when it holds a line no file
    row claimed;
  · a row not in the ledger, dated inside a completed period, is `sealed` and
    names the period: never written, never an error;
  · a row matched by `operation_code` on another day moves its line, every
    part, to the bank's day: `redated`, counted in `counts.redated`, said on
    the dry run and done by the apply;
  · a completed reconciliation the line is in stops that move: the row is
    still `matched`, `redate_blocked_by` names the reconciliation, whose read
    by its id gives the name the preview shows, the line keeps its day, and
    the file's other rows are written.

Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from tests.contract.conftest import (
    CARD_HEADER,
    CURRENT_HEADER,
    assert_refusal,
    free_statement_codes,
    read_signed,
    refused,
    replace_parts,
    send_download,
)

TITLE = "DLC*RIDES LIMA PE"


def _code() -> str:
    return f"OP{uuid4().hex[:10]}"


def _count(client, account_id: str) -> int:
    return client.get("/transactions/count", params={"account_id": account_id})["count"]


def _noon(zone: ZoneInfo, month: int, day: int) -> str:
    return datetime(2026, month, day, 12, tzinfo=zone).isoformat(timespec="seconds")


def _post(scratch, account: str, month: int, day: int, amount: int, **fields) -> str:
    """A ledger transaction at noon of the day, cleaned up with the scratch."""
    tx_id = str(uuid4())
    scratch.transactions.append(tx_id)
    scratch.client.post(
        "/transactions",
        json_body={
            "id": tx_id,
            "amount_cents": amount,
            "account_id": account,
            "date": _noon(scratch.zone, month, day),
            **fields,
        },
    )
    return tx_id


def _written(scratch, answer: dict) -> list[str]:
    """The transactions an apply created, cleaned up with the scratch."""
    ids = [row["transaction_id"] for row in answer["rows"] if row["transaction_id"]]
    scratch.transactions.extend(ids)
    return ids


def _completed(scratch, account: str, anchor: str, start: str, end: str, ending: int) -> str:
    """A reconciliation over `start` to `end` holding `anchor`, completed."""
    period = str(uuid4())
    scratch.reconciliations.append(period)
    scratch.client.post(
        "/reconciliations",
        json_body={
            "id": period,
            "account_id": account,
            "name": f"contract-import-{period[:8]}",
            "date_start": start,
            "date_end": end,
            "beginning_balance_cents": 0,
            "ending_balance_cents": ending,
        },
    )
    scratch.client.put(f"/transactions/{anchor}", json_body={"reconciliation_id": period})
    scratch.client.post(f"/reconciliations/{period}/complete")
    return period


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
    assert [r["outcome"] for r in dry["rows"]] == ["new", "new"]
    first = dry["rows"][0]
    assert (first["account_id"], first["date"], first["title"]) == (account, "2026-03-05", TITLE)
    assert (first["amount_cents"], first["transaction_type"]) == (2590, 1)
    assert (dry["rows"][1]["amount_cents"], dry["rows"][1]["transaction_type"]) == (651900, 2)
    assert first["operation_code"] == code and first["transaction_id"] is None
    assert dry["counts"]["new"] == 2
    assert _count(client, account) == 0

    applied = send_download(client, account, rows, dry_run=False)
    made = _written(scratch, applied)
    shown = ("row", "account_id", "date", "amount_cents", "transaction_type", "title", "outcome")
    assert [{k: r[k] for k in shown} for r in applied["rows"]] == [
        {k: r[k] for k in shown} for r in dry["rows"]
    ]
    assert applied["counts"] == dry["counts"]
    assert len(made) == 2 and _count(client, account) == 2
    written = client.get(f"/transactions/{made[0]}")
    assert (written["operation_code"], written["title"]) == (code, TITLE)

    again = send_download(client, account, rows, dry_run=False)
    only = again["rows"][0]
    assert only["outcome"] == "matched" and only["rule"] == "operation_code"
    assert only["bank_line_id"] == written["bank_line_id"]
    assert only["retitled"] is False
    assert again["counts"]["retitled"] == 0
    assert again["day_mismatches"] == []
    assert _count(client, account) == 2


def test_a_cards_download_lands_each_currency_on_its_own_account(scratch):
    """Sent on the card's soles account, the soles rows go to it and the dollar
    rows to the dollar account holding the same statement code, the one the
    engine names as its `statement_partner_id`
    (contract: POST /v1/transactions/import, "Accounts")."""
    client = scratch.client
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    listed = {a["id"]: a for a in client.get("/accounts")["items"]}
    assert listed[soles]["statement_partner_id"] == dollars
    assert listed[dollars]["statement_partner_id"] == soles

    rows = [
        CARD_HEADER,
        ["2026-03-11", "EDO SUSHI BAR", "S/", -49],
        ["2026-03-09", "APPLE.COM/BILL", "$", -21.17],
        ["2026-03-08", "UBER TRIP", "S/", -4.2],
    ]
    for dry_run in (True, False):
        answer = send_download(client, soles, rows, dry_run=dry_run)
        made = _written(scratch, answer)  # cleaned up whatever the checks below find
        assert [(r["row"], r["account_id"], r["outcome"]) for r in answer["rows"]] == [
            (2, soles, "new"),
            (3, dollars, "new"),
            (4, soles, "new"),
        ]
    landed = [read_signed(client, tx) for tx in made]
    assert sorted((t["account_id"], t["amount_cents"]) for t in landed) == sorted(
        [(soles, -4900), (dollars, -2117), (soles, -420)]
    )
    assert (_count(client, soles), _count(client, dollars)) == (2, 1)


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
        _written(scratch, answer)  # cleaned up whatever the checks below find
        skipped, new = answer["rows"]
        assert (skipped["row"], skipped["outcome"]) == (2, "skipped")
        assert (skipped["amount_cents"], skipped["transaction_type"]) == (0, None)
        assert skipped["transaction_id"] is None
        assert new["outcome"] == "new"
        assert (answer["counts"]["skipped"], answer["counts"]["new"]) == (1, 1)
        assert answer["day_mismatches"] == []
    assert _count(client, account) == 1


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
    assert _count(client, account) == 0


def test_a_leftover_ledger_line_is_reported_on_its_day(scratch):
    client = scratch.client
    account = scratch.account()
    ledger = [_post(scratch, account, 3, 9, -2590) for _ in range(2)]
    # a card's row: no operation code, matched by day and total
    body = send_download(
        client, account, [CARD_HEADER, ["2026-03-09", TITLE, "S/", -25.9]], dry_run=True
    )
    (only,) = body["rows"]
    assert only["outcome"] == "matched" and only["rule"] == "same_day"
    (day,) = body["day_mismatches"]
    assert day["account_id"] == account and day["date"] == "2026-03-09"
    assert (day["file_net_cents"], day["ledger_net_cents"]) == (-2590, -5180)
    assert day["unmatched_rows"] == []
    (line,) = day["unclaimed_lines"]
    assert set(line) == {"bank_line_id", "line_code", "net_cents", "parts"}
    assert line["net_cents"] == -2590
    (part,) = line["parts"]
    assert part["id"] in ledger
    # The part is the transaction response itself: a magnitude, the direction
    # in `transaction_type` (contract: "Base Conventions", "Sign convention — responses").
    assert part == client.get(f"/transactions/{part['id']}")
    assert (part["amount_cents"], part["transaction_type"]) == (2590, 1)
    assert line["bank_line_id"] == part["bank_line_id"]
    assert line["line_code"] == part["line_code"]
    assert only["bank_line_id"] != line["bank_line_id"]


def test_a_split_unclaimed_line_is_one_entry_with_every_part(scratch):
    client = scratch.client
    account = scratch.account()
    whole = _post(scratch, account, 3, 12, -10000)
    line_id = client.get(f"/transactions/{whole}")["bank_line_id"]
    parts = replace_parts(client, line_id, [-6000, -4000], scratch.transactions)

    body = send_download(
        client, account, [CARD_HEADER, ["2026-03-12", TITLE, "S/", -25.9]], dry_run=True
    )
    (only,) = body["rows"]
    assert only["outcome"] == "new"
    (day,) = body["day_mismatches"]
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
    _post(scratch, account, 3, 13, -2590)
    plus = _post(scratch, account, 3, 13, 5000)
    minus = _post(scratch, account, 3, 13, -5000)

    body = send_download(
        client, account, [CARD_HEADER, ["2026-03-13", TITLE, "S/", -25.9]], dry_run=True
    )
    (only,) = body["rows"]
    assert only["outcome"] == "matched" and only["rule"] == "same_day"
    (day,) = body["day_mismatches"]
    assert day["date"] == "2026-03-13"
    assert day["file_net_cents"] == day["ledger_net_cents"] == -2590
    assert day["unmatched_rows"] == []
    lines = day["unclaimed_lines"]
    keys = {"bank_line_id", "line_code", "net_cents", "parts"}
    assert all(set(line) == keys for line in lines)
    assert sorted(line["net_cents"] for line in lines) == [-5000, 5000]
    assert sorted(p["id"] for line in lines for p in line["parts"]) == sorted([plus, minus])


def test_a_row_inside_a_completed_period_comes_back_sealed(scratch):
    client = scratch.client
    account = scratch.account()
    anchor = _post(scratch, account, 2, 5, -100)
    period = _completed(scratch, account, anchor, "2026-02-01", "2026-02-28", -100)

    rows = [CURRENT_HEADER, ["10/02/2026", TITLE, "S/", -25.9, _code()]]
    body = send_download(client, account, rows, dry_run=False)
    (only,) = body["rows"]
    assert only["outcome"] == "sealed"
    assert only["sealed_by"] == period
    assert only["transaction_id"] is None
    assert body["counts"]["sealed"] == 1
    assert _count(client, account) == 1  # the anchor only


def test_a_code_matched_line_moves_every_part_to_the_banks_day(scratch):
    client = scratch.client
    zone = scratch.zone
    account = scratch.account()
    code = _code()
    whole = _post(scratch, account, 3, 3, -2590, operation_code=code)
    line_id = client.get(f"/transactions/{whole}")["bank_line_id"]
    parts = replace_parts(client, line_id, [-1590, -1000], scratch.transactions)

    rows = [CURRENT_HEADER, ["04/03/2026", TITLE, "S/", -25.9, code]]
    dry = send_download(client, account, rows, dry_run=True)
    (only,) = dry["rows"]
    assert only["outcome"] == "matched" and only["rule"] == "operation_code"
    assert only["redated"] is True
    assert only["redate_blocked_by"] is None
    assert dry["counts"]["redated"] == 1
    # a moved line counts on the bank's day: nothing disagrees
    assert dry["day_mismatches"] == []
    assert {_day_of(client, zone, p["id"]).date().isoformat() for p in parts} == {"2026-03-03"}

    applied = send_download(client, account, rows, dry_run=False)
    (only,) = applied["rows"]
    assert only["outcome"] == "matched"
    assert only["redated"] is True and only["redate_blocked_by"] is None
    assert applied["counts"]["redated"] == 1
    for p in parts:
        moved = _day_of(client, zone, p["id"])
        assert moved.date().isoformat() == "2026-03-04"
        assert (moved.hour, moved.minute) == (0, 0)  # 00:00, as a created row is dated


def test_a_completed_reconciliation_stops_the_move_and_the_rest_imports(scratch):
    client = scratch.client
    zone = scratch.zone
    account = scratch.account()
    code = _code()
    reconciled = _post(scratch, account, 2, 27, -2590, operation_code=code)
    period = _completed(scratch, account, reconciled, "2026-02-01", "2026-02-28", -2590)

    rows = [
        CURRENT_HEADER,
        ["02/03/2026", TITLE, "S/", -25.9, code],
        ["03/03/2026", "PAGO", "S/", -10, _code()],
    ]
    for dry_run in (True, False):
        body = send_download(client, account, rows, dry_run=dry_run)
        made = _written(scratch, body)  # cleaned up whatever the checks below find
        stopped, new = body["rows"]
        assert stopped["outcome"] == "matched" and stopped["rule"] == "operation_code"
        assert stopped["redated"] is False
        assert stopped["redate_blocked_by"] == period
        # the preview's name for it (contract: GET /v1/reconciliations/{reconciliation_id})
        named = client.get(f"/reconciliations/{stopped['redate_blocked_by']}")
        assert named["name"] == f"contract-import-{period[:8]}"
        assert new["outcome"] == "new"
        assert body["counts"]["redated"] == 0
        assert _day_of(client, zone, reconciled).date().isoformat() == "2026-02-27"
    # the stopped move is not an error: the file's other row is written
    assert len(made) == 1 and _count(client, account) == 2
    assert read_signed(client, made[0])["amount_cents"] == -1000
