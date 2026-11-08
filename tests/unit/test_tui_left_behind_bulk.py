"""The ledger's bulk edit finishes after its screen has left (`_bulk_write`).

Left before the run ends, every row is still sent, and the app shows the receipt, each
kind of refusal and a run-wide stop as the ledger would, except that a refused row is
named as the ledger showed it (`DAY · TITLE · AMOUNT`), four at most and `and N more`.
With the ledger open the notes are test_tui_bulk_edit.py's.
"""

import threading

from expense.errors import EngineError
from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.transactions import TransactionsScreen, refusal_notes
from tests.unit.helpers import app_notes, run_app, styled_stretches, wait_for
from tests.unit.test_tui_bulk_edit import (
    FILTER,
    ITEMS,
    SETTINGS_MISSING_NOTE,
    _answer_moves,
    _locked,
    _open,
    _plain,
    _settings_missing,
    _stub_ledger,
)

UNKEYED = EngineError("CONFLICT", "Engine words [not markup] naming no field.", None, 409, {})


def _rows(titles: list[str]) -> list[dict]:
    """Ledger rows t1.. with these titles, each on its own day, amount -10.00 times its number."""
    return [
        {
            **ITEMS[0],
            "id": f"t{i}",
            "title": title,
            "date": f"2026-10-{30 - i}T05:00:00Z",
            "day": f"2026-10-{30 - i}",
            "amount_cents": -1000 * i,
        }
        for i, title in enumerate(titles, start=1)
    ]


def _left_bulk(
    fake_client, monkeypatch, items=ITEMS, refusals=None, quit_instead=False, now_in=None
):
    """Select every row, `b` onto BCP Oro, leave the ledger while the first write waits,
    let the run end, and return `(the app's toasts, the paths sent)`."""
    _stub_ledger(monkeypatch, items)
    refusals = refusals or {}
    _answer_moves(fake_client, [i for i in items if f"/transactions/{i['id']}" not in refusals])
    for row_id, code in (now_in or {}).items():  # the engine moved the row to another currency
        answer = fake_client.write_responses[f"/transactions/{row_id}"]
        fake_client.write_responses[f"/transactions/{row_id}"] = {**answer, "currency_code": code}
    release, started, returned = threading.Event(), threading.Event(), threading.Event()
    sent: list[str] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        sent.append(path)
        if len(sent) == 1:
            started.set()
            release.wait(5)
        if len(sent) == len(items):
            returned.set()
        if path in refusals:
            raise refusals[path]
        return real_put(path, json_body=json_body)

    fake_client.put = put
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = TransactionsScreen(filter=FILTER)
        shown = app.screen
        await _open(app, pilot, screen)
        await pilot.press("a", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, started.is_set)
        touched: list[str] = []
        monkeypatch.setattr(screen, "_reload_fresh", lambda *a, **k: touched.append("reload"))
        monkeypatch.setattr(screen, "notify", lambda *a, **k: touched.append("toast"))
        await pilot.press("escape")  # the first esc clears the selection
        await pilot.press("escape")  # the second leaves
        await wait_for(pilot, lambda: app.screen is shown)
        if quit_instead:
            app.exit()
            release.set()
            await wait_for(pilot, returned.is_set)
            await pilot.pause()
        else:
            release.set()
            await wait_for(pilot, lambda: notes, timeout=3)
            await pilot.pause()
        assert touched == []  # nothing of the left ledger was touched
        result.extend([notes, sent])

    run_app(scenario, size=(120, 30))
    notes, sent = result
    return notes, sent


def _read(note) -> tuple[str, str, str, int]:
    """`(title, words, severity, timeout)` of a refusal toast, its markup read."""
    title, message, options = note
    return title, _plain(message), options["severity"], options["timeout"]


def test_the_receipt_shows_after_leaving_and_every_row_is_sent(fake_client, monkeypatch):
    notes, sent = _left_bulk(fake_client, monkeypatch)
    assert sent == ["/transactions/t1", "/transactions/t2", "/transactions/t3"]
    assert len(notes) == 1
    title, message, options = notes[0]
    assert (title, message, options["markup"]) == ("", "3 rows → BCP Oro", False)


def test_the_receipt_after_leaving_carries_the_currency_change_note(fake_client, monkeypatch):
    items = [{**ITEMS[0], "currency_code": "USD"}, *ITEMS[1:]]
    notes, _ = _left_bulk(fake_client, monkeypatch, items=items, now_in={"t1": "PEN"})
    assert notes[0][1] == "3 rows → BCP Oro\n1 was USD, now PEN, not converted."


def test_a_refused_kind_names_its_rows_by_day_title_and_amount(fake_client, monkeypatch):
    refusals = {f"/transactions/{k}": _locked("account_id") for k in ("t1", "t3")}
    notes, sent = _left_bulk(fake_client, monkeypatch, refusals=refusals)
    assert sent == ["/transactions/t1", "/transactions/t2", "/transactions/t3"]
    assert notes[0][:2] == ("", "1 row → BCP Oro")
    title, message, severity, timeout = _read(notes[1])
    assert (title, severity, timeout) == ("2 of 3 refused", "error", 10)
    assert message.split("\n")[-2:] == [
        "2026-09-11 · EDO SUSHI BAR · -10.00",
        "2026-09-11 · MAR DE COLAS · -30.00",
    ]
    assert "row " not in message and "rows " not in message
    stretches = styled_stretches(notes[1][1])
    assert stretches[0][2] == "$error"
    assert all(style != "$error" for _, _, style in stretches[1:])  # the rows read unstyled


def test_one_refused_row_reads_refused_alone(fake_client, monkeypatch):
    notes, _ = _left_bulk(
        fake_client, monkeypatch, refusals={"/transactions/t2": _locked("account_id")}
    )
    title, message, *_ = _read(notes[1])
    assert title == "Refused"
    assert message.endswith("\n2026-09-11 · DLC*RIDES · -20.00")


def test_six_refused_rows_show_four_then_and_2_more(fake_client, monkeypatch):
    items = _rows(["A", "B", "C", "D", "E", "F"])
    refusals = {f"/transactions/{i['id']}": _locked("account_id") for i in items}
    notes, sent = _left_bulk(fake_client, monkeypatch, items, refusals)
    assert len(sent) == 6
    assert len(notes) == 1  # no receipt: nothing landed
    title, message, *_ = _read(notes[0])
    assert title == "6 of 6 refused"
    lines = message.split("\n")
    assert [line.split(" · ")[1] for line in lines[-5:-1]] == ["A", "B", "C", "D"]
    assert lines[-1] == "and 2 more"


def test_five_refused_rows_leave_and_1_more(fake_client, monkeypatch):
    items = _rows(["A", "B", "C", "D", "E"])
    refusals = {f"/transactions/{i['id']}": _locked("account_id") for i in items}
    notes, _ = _left_bulk(fake_client, monkeypatch, items, refusals)
    assert _read(notes[0])[1].endswith("\nand 1 more")


def test_a_refusal_naming_no_row_lists_the_rows_it_met(fake_client, monkeypatch):
    refusals = {f"/transactions/{k}": UNKEYED for k in ("t1", "t2")}
    notes, _ = _left_bulk(fake_client, monkeypatch, refusals=refusals)
    title, message, *_ = _read(notes[-1])
    assert title == "2 of 3 refused"
    assert message.split("\n")[1:] == [
        "2026-09-11 · EDO SUSHI BAR · -10.00",
        "2026-09-11 · DLC*RIDES · -20.00",
    ]
    assert message.startswith("CONFLICT — Engine words [not markup] naming no field.")


def test_a_run_wide_stop_shows_its_note_after_leaving(fake_client, monkeypatch):
    notes, sent = _left_bulk(
        fake_client, monkeypatch, refusals={"/transactions/t1": _settings_missing()}
    )
    assert sent == ["/transactions/t1"]
    assert [(t, m) for t, m, _ in notes] == [SETTINGS_MISSING_NOTE]
    assert notes[0][2]["severity"] == "error"


def test_brackets_in_a_title_and_in_the_engine_words_stay_text(fake_client, monkeypatch):
    items = _rows(["[bold]Tottus[/]", "B", "C"])
    notes, _ = _left_bulk(fake_client, monkeypatch, items, {"/transactions/t1": UNKEYED})
    message = _read(notes[-1])[1]
    assert "Engine words [not markup] naming no field." in message
    assert "2026-10-29 · [bold]Tottus[/] · -10.00" in message


def test_a_refusal_with_the_apps_dim_lines_keeps_them_after_the_rows(fake_client, monkeypatch):
    duplicate = EngineError(
        "CONFLICT",
        "Operation code already exists.",
        {"operation_code": "Must be unique per account."},
        409,
        {},
        {"operation_code": "OPERATION_CODE_EXISTS"},
    )
    notes, _ = _left_bulk(fake_client, monkeypatch, refusals={"/transactions/t2": duplicate})
    assert _read(notes[1])[1] == (
        "operation_code: Must be unique per account.\n"
        "2026-09-11 · DLC*RIDES · -20.00\n"
        "That account already has a row with this operation number: "
        "look there for a duplicate."
    )
    assert [style for _, _, style in styled_stretches(notes[1][1])] == ["$error", "dim"]


def test_income_is_named_with_its_plus_as_the_ledger_draws_it(fake_client, monkeypatch):
    items = _rows(["Sueldo", "B", "C"])
    items[0]["amount_cents"] = 80000
    notes, _ = _left_bulk(fake_client, monkeypatch, items, {"/transactions/t1": UNKEYED})
    assert _read(notes[-1])[1].endswith("\n2026-10-29 · Sueldo · +800.00")


def test_quitting_mid_run_shows_nothing_more(fake_client, monkeypatch):
    notes, sent = _left_bulk(
        fake_client,
        monkeypatch,
        refusals={"/transactions/t1": _locked("account_id")},
        quit_instead=True,
    )
    assert notes == []
    # quitting stops nothing already running: the worker thread still sends every row
    assert sent == ["/transactions/t1", "/transactions/t2", "/transactions/t3"]


def test_an_open_ledger_still_names_its_rows_by_number():
    """Without `row_lines` the rows read `row 2` / `rows 1, 3`, as the ledger shows them
    (the screen's own notes are test_tui_bulk_edit.py's)."""
    failed = [("t1", 1, "k", "words"), ("t2", 2, "j", "other"), ("t3", 3, "k", "words")]
    assert [_plain(n) for n in refusal_notes(failed)] == [
        "words\nrows 1, 3",
        "other\nrow 2",
    ]
