# The `?` card's leftovers, and the Backlog's clean-up

Two small things you see on the `?` card, found while the small fixes on screen ran (done on
2026-11-07) and not fixed there; and, merged in at the owner's ask on 2026-11-07, every clean-up
item of [todo.md](../todo.md)'s Backlog that waits on nothing: tests, comments and small code
gaps that change nothing you see.

**Status: approved on 2026-11-07, its question answered; the loop is running.** It waits on no
other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

1. **The card's side gutters show the screen behind it.** With the card open over the ledger,
   the ledger's own rule peeks out as a one-cell `─` on each side of the card's frame (at 80×24,
   columns 3 and 76 of row 4; the wide card the same at columns 3 and 136); over the "no
   statement" list, bits of the Statements screen show there (`St`, `▸`, `In`, `!`). Every
   mockup of the card draws those gutters blank.
2. **The Statements account list's card lists page keys that do nothing.** With the panel
   closed, the account list's card lists `pgdn Load the next 10 rows under these`, `pgdn Next
   page` and `pgup Previous page`; none of them works there and the footer shows none of them.
   A card lists a key only while it works ([decisions.md](../decisions.md) "The `?` card shows
   whole and lists only keys that work"), so this one needs no question.
3. **The clean-up below** is small work found by earlier specs. None of it changes what you see;
   it keeps the tests trustworthy and the code and comments saying what is so.

## The clean-up

### The drift check

- **It misreads a nested union.** For an answer `anyOf [X, anyOf [Y, Z]]` it checks against X
  alone, and for `anyOf [anyOf [Y, Z]]` it says the contract holds no JSON answer, where both
  should say the answer comes in more than one shape (`_object_schema` and
  `answered_in_many_shapes` in [check_fixture_drift.py](../../scripts/check_fixture_drift.py)).
  No marked answer has such a shape today.
- **It skips a test file's own `**fields` builders.** It reads a field passed by name only to a
  `**fields` builder in [helpers.py](../../tests/unit/helpers.py); the ones local to one test
  file (`_kept`, `_statement`, …) are not read.

### Flaky and weak unit tests

- **Two unit tests fail now and then in CI**, each a worker's hand-back querying a widget that
  has gone: `test_a_statement_created_after_leaving_opens_its_accounts_panel`
  ([test_tui_statements.py](../../tests/unit/test_tui_statements.py); `NoMatches '#crumb' on
  StatementsScreen`, runs 42281849326, 42283565489, 42284942729, 42291172306, 42303070384 and
  42310670430 on 2026-11-06) and
  `test_an_emptied_field_never_sends_null_where_the_engine_refuses_it[bank_line-operation]`
  ([test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py); `NoMatches '#brand' on
  HomeScreen`, run 41510519928 on 2026-11-02).
- **`test_coming_back_from_a_statement_keeps_the_panel_on_the_same_row` waits weakly**
  ([test_tui_statements.py](../../tests/unit/test_tui_statements.py) ~line 567): it waits for
  `_statement_list is not None`, which the old list already passes, so it can pass without
  proving the cursor after the read, or fail at random under the parallel run. It should wait
  for the read's cursor on `b2`.

### After leaving a screen

- **The after-leaving code has small gaps.** `_landed_after_leaving` in
  [create_forms.py](../../expense/tui/screens/create_forms.py) reads `left_behind.part.report`
  unguarded; `_opening_saved`'s `part` has no type. No test drives the real `esc` (the tests pop
  the screen), none covers an account save whose only write is the account, and the
  new-statement test calls `_created` by hand instead of driving the late answer. The comment on
  the balances save's `LeftBehind` in [statements.py](../../expense/tui/screens/statements.py)
  names `_write_finished_after_leaving` where the words come from `_say_after_leaving`.
- **New statement's refusal after leaving is untested under a 5xx or no answer.** It is a bar
  form and follows `open_it_again` ([_form.py](../../expense/tui/screens/_form.py)), but no test
  drives it.

### Quitting

- **The quit-question tests need tidying.**
  [test_tui_quit_asks.py](../../tests/unit/test_tui_quit_asks.py): the LOG bar `y` test records
  whether the bar is still in the stack but never asserts it; the `bar_empty` helper sits
  between tests; two preview screens are imported inside test bodies; the import hand-back test
  reads `seen_app` before assigning it; no test covers a second `ctrl+q` quitting at once once
  every save ended while the question was up. A docstring in
  [test_tui_left_behind_account_form.py](../../tests/unit/test_tui_left_behind_account_form.py)
  (~line 110) wraps mid-phrase.
- **A screen gone before its save's thread starts would raise instead of reporting.** The LOG
  bar, bank import and statement upload workers read `self.app` for `counted_save`
  ([_base.py](../../expense/tui/screens/_base.py)) before their `try`; it cannot happen today,
  since `esc` is refused while they save.
- **Setup's `esc Quit` leaves through `app.exit()`, not the shared quit.** It is refused while
  setup saves, so no save is lost; it is the one quit not going through `action_quit`
  ([app.py](../../expense/tui/app.py)).

### The LOG bar's peek

- **No LOG bar test checks the peek's title and count on a two-currency pick** (`$visa %usd`).
- **Two comments in [log_bar.py](../../expense/tui/screens/log_bar.py) describe the peek's old
  border:** the `CHROME_LINES` comment and `AccountPeek._heading`'s docstring.

### Shared copies, comments and guards

- **One unit test writes the engine address and token itself.**
  [test_no_read_only_fields.py](../../tests/unit/test_no_read_only_fields.py) (lines 174, 187,
  231) where `ENGINE_URL` and `ENGINE_TOKEN` in helpers.py hold them.
- **No test draws a marked or refused part row with an income.** In the Edit form's parts table
  both rows print the same cell as the locked row, which a test pins with `+3,200.00`, but
  neither has a test of its own (`parts_lines` in
  [parts_table.py](../../expense/tui/widgets/parts_table.py)).
- **The `TRANSACTION_RULE` comment speaks of lists only.** Its comment in
  [theme.py](../../expense/tui/theme.py) says the rule covers an amount "in a list"; it also
  covers a transaction named outside one (the question before a delete, a note after you leave)
  and the Edit form's parts count line, a sum, as [tui.md](../tui.md) "Amounts" says.
- **The footer guard has gaps.** `test_no_screen_draws_textuals_own_footer`
  ([test_tui_fitting_footer.py](../../tests/unit/test_tui_fitting_footer.py)) misses attribute
  access (`widgets.Footer()`), skips any file named `footer.py` rather than that one path, and
  its module docstring speaks of list screens only; `FittingFooter`'s docstring
  ([footer.py](../../expense/tui/widgets/footer.py)) says `?` lists a left-out key without "on a
  screen that has one".
- **`(unnamed)` for a blank name is written out four times** (`not_done_line` in
  [_base.py](../../expense/tui/screens/_base.py) and the account, category and hashtag lists);
  `title_or_untitled` is the one shared copy for titles, and names have none.

### The live tests

- **Live tests read a refused write back by hand.** test_statement_import.py,
  test_bank_import.py, test_reserved_name_held.py, test_bank_lines.py,
  test_resources_lifecycle.py, test_statement_currencies.py, test_statement_order.py and
  test_statements_lifecycle.py in [tests/contract/](../../tests/contract/) write "refused, then
  the same read" inline instead of using `refused_keeping` in conftest.py; some share one before
  read across a loop or use `before` in later asserts, which stays by hand.

## What it must do

Point 1 as its question below picks; point 2 lists the page keys only while they work, as the
statements panel's card already does; every item under "The clean-up" is done, and nothing else
you see changes.

## How the owner knows it is done

1. With the `?` card open over the ledger at 80×24 and at 140×24, and over the "no statement"
   list at 80×24, the gutters beside the card show as picked.
2. With the panel closed, the Statements account list's card lists no `pgdn` or `pgup` row
   while those keys do nothing there.
3. The unit suite passes.
4. The drift check and the live contract suite pass against the practice engine.

## Questions for the owner

1. **The gutters beside the `?` card?** Pick in
   [the mockup](../mockups/expense-world-help-card-gutters.html):
   - **A.** Blank, as every mockup draws them: the card covers what is behind it right up to
     its frame.
   - **B.** As today: the screen behind shows through, one cell each side.
   **Recommended:** A. The card reads as one block, and nothing half-drawn shows beside it.

   **Picked: A** (2026-11-07).

---

## Tasks

Approved 2026-11-07. Each task's "passes if…" is written when it starts. The clean-up runs
first.

All done; the acceptance check and the doc sweep follow.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The drift check reads a nested union of lists the old way.** `_list_items` in
  [check_fixture_drift.py](../../scripts/check_fixture_drift.py) reads `anyOf [A[], anyOf [B[],
  C[]]]` as A's items alone. No marked answer has such a shape today.
- **No unit test pins a union that contains itself.** `_alternatives` in
  [check_fixture_drift.py](../../scripts/check_fixture_drift.py) drops a `$ref` already seen on
  its path, so such a union ends; nothing in
  [test_fixture_drift_script.py](../../tests/unit/test_fixture_drift_script.py) proves it.
- **A screen's hand-back can touch its widgets after an `await`, once the screen has gone.**
  `call_while_attached` ([_base.py](../../expense/tui/screens/_base.py)) checks the screen is
  still there only before a coroutine hand-back starts; `StatementsScreen._show` and
  `_open_panel` ([statements.py](../../expense/tui/screens/statements.py)), and any `_show` with
  work after `await super()._show()`, query widgets after an await. `esc` or a quit during that
  mount raises `NoMatches` in the worker and the app crashes. The fix is one shared re-check
  after the await, with its own test.
