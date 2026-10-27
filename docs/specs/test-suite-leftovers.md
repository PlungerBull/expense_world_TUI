# Leftovers in the test suites

**Status: draft, for the owner to rewrite or approve. Its tasks are drafted when the owner names
it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file
is deleted.

---

## Why

Small things found while doing the statement catch-up's leftovers (2026-10-25), and while
proving a held reserved name on the Edit form (points 9 and 10, 2026-10-25), and while catching
up with reading bank lines by their ids (point 11, 2026-10-27), and while making lists show
bracketed names whole (points 12 and 13, 2026-10-27), not fixed there.
All of them are inside the test suites and their tools: nothing you see changes, and no engine
change is needed.

## What it must do

1. **One account-record builder for the unit suite**: `_account` in
   [test_cmd_import.py](../../tests/unit/test_cmd_import.py),
   [test_tui_account_kind.py](../../tests/unit/test_tui_account_kind.py) and
   [test_tui_card_statement.py](../../tests/unit/test_tui_card_statement.py) each build the
   engine's account record their own way; one builder in
   [helpers.py](../../tests/unit/helpers.py). And about 20 tests in test_cmd_import.py repeat
   `_mock_existing(accounts=[_account()], categories=[], hashtags=[])`, which the file's own
   `_seeded_account()` does.
2. **The fake engine's answers are used, not rebuilt**:
   `test_saved_it_says_so_and_the_panel_lands_on_the_new_statement` in test_tui_card_statement.py
   builds the card create's answer by hand, which the fake engine builds already.
3. **The drift check covers more answers**: the update, a bank line's read and the
   reconciliation create's builders carry `@answer_of` too; a card's `twin` half is checked
   against its own schema; a marked answer's extra keys are checked against its own endpoint;
   `answer_of` refuses a second builder for one endpoint; and an answer the contract allows in
   more than one shape is named as such, not as "no JSON answer"
   ([the drift script](../../scripts/check_fixture_drift.py)).
4. **A fixture quotes the engine's current `GAP` warning**: the sentence in
   [test_tui_reconcile_detail.py](../../tests/unit/test_tui_reconcile_detail.py) ("…sealed by
   nothing", 2026-02-25 to 2026-04-01) predates the contract's wording, and its last day is the
   period's first day.
5. **`stub_home_month` says what it replaces**: in helpers.py it also replaces the settings
   with a bare object, so a respx test that calls it fails on `engine_url`; its name or
   docstring says so, or it stops doing it.
6. **One copy of each contract-suite helper, the rest of them**: `_transaction_ids` in
   [test_account_kind.py](../../tests/contract/test_account_kind.py) is `live_ids`;
   [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) sends
   the statement order inline instead of through `send_order`; `_item` in
   [test_create_into_reconciliation.py](../../tests/contract/test_create_into_reconciliation.py)
   repeats `Scratch`'s create body; and the contract files that build records through their own
   helpers build them through `Scratch` ([conftest.py](../../tests/contract/conftest.py)).
7. **The practice-user cleaner reads every page**: `_delete_transactions` in
   [clean_practice_user.py](../../scripts/clean_practice_user.py) stops on a page holding only
   refused deletes, so deletable ones past it stay.
8. **The drift script's docstring points to runtime.md** instead of repeating it: its REQUIRED
   FIELDS and KNOWN LIMITATION blocks copy [runtime.md](../runtime.md) "Fixture drift", where
   its CONTRACT VERSION block already just links there.
9. **Four test comments say what their rows prove.** In
   [test_errors.py](../../tests/unit/test_errors.py), the comments heading the refusal rows
   say "pending-hashtag-manage 4 B, both refusals, and 5 B", "pending-hashtag-manage 7 B",
   "archived-account 3 A" and "account-to-person 4 B"; each says what its rows prove instead.
10. **The Edit form's shared hashtag-refusal test checks what it says.**
    `test_a_hashtag_refusal_shows_under_the_parts_as_sent` in
    [test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py) runs every hashtag refusal,
    `RESERVED_NAME_HELD` among them, but when a reason has no line of the app's it checks
    nothing, so it would pass with one showing. It proves no line of the app's shows for those
    reasons, and for every reason that "Nothing was saved." shows and one write was sent.
11. **A live test checks a statement upload's words for a future-dated line.** The engine names
    the line, "Row <place>: Must not be in the future." on `rows.<place>.date`, on POST
    /reconciliations/import as on the other two imports (contract version `46e2fdf6e11d7548`),
    but the live suite drives that route only for a held reserved name; one test sends a made-up
    statement PDF with a future-dated line and checks the words.
12. **One shared step reads a refused write back in the live suite.**
    [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py) (around lines 233
    and 293) writes by hand the refused-then-unchanged read that `_refused_unwritten` in
    [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) does;
    one shared step in the contract [conftest.py](../../tests/contract/conftest.py) serves both.
13. **Two heads are pinned showing a bracketed name whole.** The bank import's account list
    (`account_lines`) and its `Preview · <account>` head
    ([bank_import.py](../../expense/tui/screens/bank_import.py)), and the reconciliation
    detail's head naming the statement and its account
    ([reconciliations.py](../../expense/tui/screens/reconciliations.py)), show `[like this]`
    whole in the app (the tester's check of 2026-10-27), but no test in
    [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) pins them.

## How the owner knows it is done

1. The unit and live suites pass, and each point above has its test or its single copy.
2. The drift check against the practice engine is clean.

## Questions for the owner

None.
