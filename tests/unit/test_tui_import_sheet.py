"""The import's review (`expense import sheet <file>` opens the app on it): the table of
accounts to make, the form behind `⏎`, `^s` held while a row says `?`, the dry run's body and
the one question before the apply, and the engine's refusals on their rows.

The engine is the shared FakeClient with its import route scripted: each call answers the
next item, an exception raised. The first dry run is the command's (test_cmd_import.py); the
review starts from the table it left.
"""

import pytest

from expense.config import Config
from expense.errors import EngineError
from expense.import_.engine import SheetReview, names_table
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.import_sheet import (
    AccountRow,
    ImportSheetScreen,
    SheetAccountScreen,
    makes_cell,
    ready_question,
    still_needed,
)
from expense.tui.screens.modals import ConfirmModal
from expense.tui.theme import PALETTE
from tests.unit.helpers import (
    ENGINE_BANKS,
    enter_values,
    refusal_block,
    render_text,
    run_app,
    sheet_import_answer,
    sheet_name_use,
    sheet_row,
    shown,
    toasts_shown,
    wait_for,
)

CFG = Config(engine_url="https://api.example.com", token="ewe_pat_test")
DATA = b"PK\x03\x04 a made-up workbook"
ROWS = 4191
#: The engine's count of the apply and the dry run alike: every row new but two of zero.
COUNTS = {
    "new": 4189,
    "matched": 0,
    "sealed": 0,
    "skipped": 2,
    "opening_balances": 0,
    "split_lines": 0,
    "split_rows": 0,
}


def _guess(kind: str | None, bank: str | None, last4: str | None, *currencies: str) -> dict:
    return {"kind": kind, "bank_code": bank, "last4": last4, "currencies": list(currencies)}


def _review(accounts: list[dict], categories=(), hashtags=()) -> SheetReview:
    """The review opened on a sheet of `ROWS` rows using these names; a category or hashtag
    is one to make."""
    answer = sheet_import_answer(
        accounts=accounts,
        categories=[sheet_name_use(name, 10) for name in categories],
        hashtags=[sheet_name_use(name, 10) for name in hashtags],
        rows=[sheet_row(r) for r in range(2, ROWS + 2)],
    )
    return SheetReview("libro.xlsx", DATA, names_table(answer), ROWS, CFG)


#: Five accounts to make: a full guess, one with no last 4, two the engine does not read and
#: one it half-reads at another bank.
ACCOUNTS = [
    sheet_name_use(
        "BCP 1234", 1203, suggestion=_guess("bank", "BCP", "1234", "PEN"), currencies=["PEN"]
    ),
    sheet_name_use(
        "BCP Sueldo Soles", 312, suggestion=_guess("bank", "BCP", None, "PEN"), currencies=["PEN"]
    ),
    sheet_name_use("VISA Infinite Sapphire", 1846, currencies=["PEN", "USD"]),
    sheet_name_use("ALEJO", 58, currencies=["PEN", "USD"]),
]
#: Every row set: a full guess and a bank with a last 4.
READY = [
    sheet_name_use(
        "BCP 1234", 1203, suggestion=_guess("bank", "BCP", "1234", "PEN"), currencies=["PEN"]
    ),
    sheet_name_use(
        "IBK 4321",
        212,
        suggestion=_guess("bank", "IBK", "4321", "PEN", "USD"),
        currencies=["PEN", "USD"],
    ),
    sheet_name_use("BCP-0001", 9, "acc-have", currencies=["PEN"]),
]


def _answer(dry_run: bool, created: tuple[int, int, int] = (2, 2, 1)) -> dict:
    accounts, categories, hashtags = created
    return sheet_import_answer(
        dry_run=dry_run,
        created={"accounts": accounts, "categories": categories, "hashtags": hashtags},
        counts=COUNTS,
    )


def _refusal(fields: dict[str, str]) -> EngineError:
    return EngineError("VALIDATION_ERROR", "Import validation failed.", fields, 422, {})


def _open(review: SheetReview, body, **options):
    """Run `body(pilot, app, screen)` on the review once it has read the banks."""

    async def scenario(pilot, app):
        screen = ImportSheetScreen(review)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._statement_banks is not None)
        return await body(pilot, app, screen)

    return run_app(scenario, **options)


def _text(screen) -> list[str]:
    return shown(screen.query_one("#import-body")).splitlines()


def _note(app) -> str | None:
    """Home's line under the rule as drawn, in the success style; None while it is hidden."""
    note = app.screen.query_one("#note")
    if not note.display:
        return None
    return render_text(note.content).strip()


def _sent(fake_client) -> list[dict]:
    return [body for _path, body in fake_client.posts]


# ---- what the table says ----------------------------------------------------------
def test_the_review_lists_each_account_to_make_and_what_is_still_asked(fake_client):
    """The head counts the rows and what is made; each row says what the engine's guess
    makes, `? last 4` and `? pick a kind` where it has none; the lists of categories and
    hashtags follow, then how many accounts still need what."""

    async def body(pilot, app, screen):
        assert _text(screen) == [
            "4,191 rows · 4 accounts, 3 categories and 2 hashtags to make",
            "SHEET NAME               CUR          ROWS   MAKES                   ARCHIVE",
            "BCP 1234                 PEN         1,203   bank · BCP · 1234",
            "BCP Sueldo Soles         PEN           312   bank · BCP · ? last 4",
            "VISA Infinite Sapphire   PEN + USD   1,846   ? pick a kind",
            "ALEJO                    PEN + USD      58   ? pick a kind",
            "Categories   Comida · Transporte · SALDO INICIAL",
            "Hashtags     Personal · Trabajo",
            "1 account still needs a last 4, 2 a kind.",
        ]

    _open(
        _review(ACCOUNTS, ["Comida", "Transporte", "SALDO INICIAL"], ["Personal", "Trabajo"]), body
    )


def test_a_row_reads_its_kind_and_the_pieces_it_lacks_in_the_warning_style():
    warn = PALETTE.warning
    held = {"type": "bank", "bank": "BCP", "last4": "1234"}
    assert makes_cell(held).plain == "bank · BCP · 1234"
    assert makes_cell({"type": "bank", "bank": "BCP"}).plain == "bank · BCP · ? last 4"
    assert makes_cell({"type": "bank", "last4": "1234"}).plain == "bank · ? bank · 1234"
    assert makes_cell({"type": "person", "name": "ALEJO"}).plain == "person · ALEJO"
    assert makes_cell({"type": "cash", "name": "Caja"}).plain == "cash"
    unset = makes_cell({})
    assert (unset.plain, unset.style) == ("? pick a kind", warn)
    half = makes_cell({"type": "bank", "bank": "BCP"})
    assert [(half.plain[s.start : s.end], s.style) for s in half.spans] == [("? last 4", warn)]


# ---- the form behind ⏎ ---------------------------------------------------------
def test_enter_opens_the_form_from_the_suggestion_and_ctrl_s_sets_the_row_writing_nothing(
    fake_client,
):
    """ALEJO is no kind: the form opens on TYPE with the sheet's currencies read-only and
    its name filled; picking person and `^s` returns to the review with the row set."""

    async def body(pilot, app, screen):
        await pilot.press("down", "down", "down", "enter")  # ALEJO
        form = app.screen
        assert isinstance(form, SheetAccountScreen)
        assert form.crumb == ("Import sheet", "ALEJO")
        assert (form._key, form._values.get("type")) == ("type", None)
        assert form._sequence() == ["type", "bank", "last4", "currencies", "archive"]
        await enter_values(pilot, "person")
        assert form._key == "name"
        assert form._values["name"] == "ALEJO"
        summary = shown(form.query_one("#summary"))
        assert "PEN · USD  the sheet's" in summary
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is screen)
        assert "ALEJO                    PEN + USD      58   person · ALEJO" in _text(screen)[5]
        assert fake_client.posts == []

    _open(_review(ACCOUNTS), body)


def test_esc_on_the_form_leaves_the_row_as_it_was(fake_client):
    async def body(pilot, app, screen):
        await pilot.press("enter")  # BCP 1234, as the engine guessed it
        await enter_values(pilot, "ibk")
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert "bank · BCP · 1234" in _text(screen)[2]

    _open(_review(ACCOUNTS), body)


BANK_LINES = ["type", "bank", "last4", "currencies"]


@pytest.mark.parametrize(
    ("values", "lines"),
    [
        ({"type": "bank", "bank": "BCP"}, [*BANK_LINES, "statement_code", "archive"]),
        ({"type": "bank", "bank": "IBK"}, [*BANK_LINES, "archive"]),
        ({"type": "person"}, ["type", "name", "currencies", "archive"]),
        ({"type": "cash"}, ["type", "currencies", "archive"]),
    ],
    ids=["bank read", "bank not read", "person", "cash"],
)
def test_the_form_has_the_new_account_lines_less_color_plus_archive(values, lines):
    """The statement code line only while BANK is a code `GET /banks` lists, and no color
    line, which `create` refuses; a code the form has no line for is not handed back."""
    held = {"name": "x", "last4": "1234", "statement_code": "SIG", "archive": "no", **values}
    form = SheetAccountScreen("x", ("PEN",), held, ENGINE_BANKS)
    assert form._sequence() == lines
    assert ("statement_code" in form._payload()) == ("statement_code" in lines)


@pytest.mark.parametrize(
    ("values", "line"),
    [
        ({"type": "bank", "bank": "BCP"}, "last4"),
        ({"type": "bank", "last4": "1234"}, "bank"),
        ({}, "type"),
        ({"type": "bank", "bank": "BCP", "last4": "1234"}, "type"),
    ],
    ids=["? last 4", "? bank", "? pick a kind", "nothing asked"],
)
def test_the_form_opens_on_the_line_the_row_asks_for(fake_client, values, line):
    """`⏎` on a row lands on the piece its `?` names, else on the first line."""

    async def scenario(pilot, app):
        form = SheetAccountScreen(
            "x", ("PEN",), {"name": "x", "archive": "no", **values}, ENGINE_BANKS
        )
        await app.push_screen(form)
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        assert form._key == line

    run_app(scenario)


def test_type_says_nothing_is_kept_while_the_row_has_no_kind():
    bare = SheetAccountScreen("x", ("PEN",), {}, ENGINE_BANKS)
    kept = SheetAccountScreen("x", ("PEN",), {"type": "bank"}, ENGINE_BANKS)
    assert "keeps" not in bare._hint_for("type") and "keeps bank" in kept._hint_for("type")


def test_the_app_given_a_review_opens_on_it_with_the_settings_the_command_read(
    fake_client, monkeypatch
):
    """`launch` takes the review's settings and reads the settings file no more (a pipe
    gives its contents once), so the app opens on the review, not on Setup."""
    import asyncio

    from expense.tui import app as tui_app

    held = []
    monkeypatch.setattr("expense.config.load_usable", lambda: pytest.fail("read the file again"))
    monkeypatch.setattr("expense.config.hold", held.append)
    monkeypatch.setattr("expense.reads.fetch_number_format", lambda cfg, **kw: None)
    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui_app.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(tui_app, "get_verbose", lambda ctx: False)
    seen = []

    def run(self, **kw):
        async def drive():
            async with self.run_test() as pilot:
                await wait_for(pilot, lambda: isinstance(self.screen, ImportSheetScreen))
                seen.append(self._setup)

        asyncio.run(drive())

    monkeypatch.setattr(tui_app.ExpenseApp, "run", run)
    review = _review(ACCOUNTS)
    tui_app.launch(None, review)
    assert (held, seen) == ([CFG], [False])


def test_a_name_the_engine_proposes_an_account_for_keeps_its_row_and_makes_nothing(
    fake_client, monkeypatch
):
    """`yours · <account>` in the dim style, left out of the head's count; `⏎` and `a` skip
    it (its form never opens, nothing is archived)."""
    monkeypatch.setattr(
        "expense.tui.screens.import_sheet.load_account_name_map", lambda: {"acc-have": "BCP-0001"}
    )

    async def body(pilot, app, screen):
        await wait_for(pilot, lambda: "yours · BCP-0001" in "\n".join(_text(screen)))
        lines = _text(screen)
        assert lines[0] == "4,191 rows · 1 account, 0 categories and 0 hashtags to make"
        assert lines[3].startswith("BCP-0001") and lines[3].endswith("yours · BCP-0001")
        await pilot.press("down", "enter", "a")  # onto the proposed row
        assert screen._cursor == 1 and app.screen is screen
        assert screen._rows[1].values == {}
        assert "archive" not in _text(screen)[3].replace("ARCHIVE", "")

    _open(_review([READY[0], READY[2]]), body)


def test_the_line_under_the_table_counts_the_rows_once_when_all_three_are_asked():
    entry = _review(ACCOUNTS).table[0]
    rows = [
        AccountRow(entry, {"type": "bank", "last4": "1234"}),
        AccountRow(entry, {"type": "bank", "bank": "BCP"}),
        AccountRow(entry, {}),
    ]
    assert still_needed(rows) == "3 accounts still need a bank, a last 4 or a kind."


def test_a_form_holding_archive_yes_keeps_it_on_enter(fake_client):
    async def body(pilot, app, screen):
        await pilot.press("a", "enter")  # BCP 1234 archived, then its form
        await pilot.press("enter", "enter", "enter", "enter")  # type, bank, last 4, code kept
        assert app.screen._key == "archive"
        assert app.screen._values["archive"] == "yes"
        await pilot.press("enter")  # the last line: done
        await wait_for(pilot, lambda: app.screen is screen)
        assert "archive" in _text(screen)[2]

    _open(_review(ACCOUNTS), body)


# ---- ^s ------------------------------------------------------------------------
def test_ctrl_s_is_held_while_any_row_says_a_question_mark(fake_client):
    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: toasts_shown(app))
        assert toasts_shown(app) == ["1 account still needs a last 4, 2 a kind."]
        assert fake_client.posts == []

    _open(_review(ACCOUNTS), body, toasts=True)


def test_the_dry_run_sends_create_with_ids_kept_and_names_at_them_then_only_y_applies(fake_client):
    """The review's body: the accounts to make with the lines set (IBK archived with `a`),
    the categories and hashtags missing, `names` at the made ids and at the proposed one;
    the same body again after `n`, and with `dry_run` false after `y`; the question is the
    engine's count; the app then ends with the one line."""
    fake_client.post_queue.extend([_answer(True), _answer(True), _answer(False)])

    async def body(pilot, app, screen):
        await pilot.press("down", "a", "ctrl+s")  # IBK 4321 archived
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == (
            "Ready: 2 accounts, 2 categories and 1 hashtag made; "
            "4,189 rows imported and 2 rows of zero skipped."
        )
        assert app.screen._message == "Import? Only y imports."
        first = _sent(fake_client)[0]
        assert first["dry_run"] is True and fake_client.posts[0][0] == "/transactions/import-sheet"
        accounts = first["create"]["accounts"]
        assert [(a["kind"], a["bank_code"], a["last4"], a["archived"]) for a in accounts] == [
            ("bank", "BCP", "1234", False),
            ("bank", "IBK", "4321", True),
        ]
        assert [a["currencies"] for a in accounts] == [["PEN"], ["PEN", "USD"]]
        made = {
            c["name"]: c["id"] for key in ("categories", "hashtags") for c in first["create"][key]
        }
        assert sorted(made) == ["Comida", "Personal", "Transporte"]
        assert first["names"]["accounts"] == [
            {"name": "BCP 1234", "account_id": accounts[0]["id"]},
            {"name": "IBK 4321", "account_id": accounts[1]["id"]},
            {"name": "BCP-0001", "account_id": "acc-have"},
        ]
        assert [(c["name"], c["category_id"]) for c in first["names"]["categories"]] == [
            (n, made[n]) for n in ("Comida", "Transporte")
        ]
        assert [(c["name"], c["hashtag_id"]) for c in first["names"]["hashtags"]] == [
            ("Personal", made["Personal"])
        ]

        await pilot.press("n")  # anything but y: back on the review, nothing applied
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(fake_client.posts) == 1
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert _sent(fake_client)[1] == first  # the same ids and the same body, sent again
        await pilot.press("y")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        assert _sent(fake_client)[2] == {**first, "dry_run": False}
        assert _note(app) == "Imported 4,189 rows · 2 accounts, 2 categories and 1 hashtag made."

    _open(_review(READY, ["Comida", "Transporte"], ["Personal"]), body)


def test_the_question_names_what_the_engine_counted_beyond_new_and_zero_rows():
    answer = sheet_import_answer(
        created={"accounts": 1, "categories": 0, "hashtags": 0},
        counts={**COUNTS, "new": 1, "matched": 3, "sealed": 1, "skipped": 0},
    )
    assert ready_question(answer) == (
        "Ready: 1 account, 0 categories and 0 hashtags made; "
        "1 row imported, 3 rows already in the ledger and 1 row on a closed statement's day."
    )


def test_esc_leaves_for_home_with_nothing_written_and_the_app_says_so(fake_client):
    async def body(pilot, app, screen):
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        assert _note(app) == "Nothing was imported."
        assert fake_client.posts == []
        # a modal over Home (the `?` card) leaves it; a screen opening over Home takes it away
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: not isinstance(app.screen, HomeScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        assert _note(app) == "Nothing was imported."
        await pilot.press("plus")  # the LOG bar: a screen over Home
        await wait_for(pilot, lambda: not isinstance(app.screen, HomeScreen))
        assert app.screen_stack[0].query_one("#note").display is False

    _open(_review(ACCOUNTS), body)


# ---- the engine's refusals --------------------------------------------------------
def test_a_refused_account_marks_its_row_and_its_form_opens_on_the_line_with_the_words(
    fake_client,
):
    """The cursor lands on the refused row, `!` in front of its MAKES, the engine's words
    under the table and that nothing was written; `⏎` opens its form with the same words, the
    cursor on LAST 4; `^s` there takes the row back."""
    words = "An account named IBK-4321 already exists."
    # a proposed row comes first: `create.accounts.1` is the second row made, the third row
    fake_client.post_queue.append(_refusal({"create.accounts.1.last4": words}))

    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: "Nothing was written." in "\n".join(_text(screen)))
        lines = _text(screen)
        assert lines[4].startswith("IBK 4321") and "! bank · IBK · 4321" in lines[4]
        assert not any("!" in line for line in lines[2:4])  # neither the proposed nor BCP 1234
        assert lines[-2:] == [f"! IBK 4321: {words}", "Nothing was written."]
        assert screen._cursor == 2 and app.screen is screen
        await pilot.press("enter")
        form = app.screen
        assert (form._key, refusal_block(form)) == ("last4", f"Failed\n{words}")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is screen)
        assert not any("!" in line for line in _text(screen))

    _open(_review([READY[2], READY[0], READY[1]], ["Comida"], ["Personal"]), body)


def test_a_refused_hashtag_reads_under_the_hashtags_line_and_marks_no_row(fake_client):
    words = "A hashtag named personal already exists."
    fake_client.post_queue.append(_refusal({"create.hashtags.0.name": words}))

    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: "Nothing was written." in "\n".join(_text(screen)))
        lines = _text(screen)
        assert lines[-3:] == ["Hashtags     Personal", f"! {words}", "Nothing was written."]
        assert not any("! bank" in line for line in lines)

    _open(_review(READY[:2], ["Comida"], ["Personal"]), body)


def test_any_other_refusal_reads_in_the_engines_words_under_the_table(fake_client):
    words = "Must reference an active, non-archived account."
    fake_client.post_queue.append(_refusal({"names.accounts.2.account_id": words}))

    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: "Nothing was written." in "\n".join(_text(screen)))
        text = " ".join(" ".join(_text(screen)).split())
        assert "VALIDATION_ERROR — Import validation failed." in text and words in text
        assert not any("! bank" in line for line in _text(screen))

    _open(_review(READY), body)
