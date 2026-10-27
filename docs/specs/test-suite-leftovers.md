# Leftovers in the test suites

**Status: draft, for the owner to rewrite or approve; on 2026-10-27 the owner moved the
future-dated line's live test out and brought in the test-only items of todo.md's backlog. Its
tasks are drafted when the owner names it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file
is deleted.

---

## Why

Small things found while doing the statement catch-up's leftovers (2026-10-25), and while
proving a held reserved name on the Edit form (points 9 and 10, 2026-10-25), and while making
lists show bracketed names whole (points 11 and 12, 2026-10-27), not fixed there; and the
backlog's items that live only in the tests and their tools (points 13 to 18, and the end of
point 6), brought in by the owner on 2026-10-27.
All of them are inside the test suites and their tools: nothing you see changes, and no engine
change is needed.

## What it must do

1. **One account-record builder for the unit suite**: `_account` in
   [test_tui_account_kind.py](../../tests/unit/test_tui_account_kind.py) and
   [test_tui_card_statement.py](../../tests/unit/test_tui_card_statement.py) each build the
   engine's account record their own way; one builder in
   [helpers.py](../../tests/unit/helpers.py).
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
   repeats `Scratch`'s create body; the contract files that build records through their own
   helpers build them through `Scratch` ([conftest.py](../../tests/contract/conftest.py)); and
   `_safe` and `_refused`, defined again in about 20 files in
   [tests/contract/](../../tests/contract/), have one copy in conftest.py beside `client`,
   `reason_on` and `statuses`.
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
11. **One shared step reads a refused write back in the live suite.**
    [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py) (around lines 233
    and 293) writes by hand the refused-then-unchanged read that `_refused_unwritten` in
    [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) does;
    one shared step in the contract [conftest.py](../../tests/contract/conftest.py) serves both.
12. **Two heads are pinned showing a bracketed name whole.** The bank import's account list
    (`account_lines`) and its `Preview · <account>` head
    ([bank_import.py](../../expense/tui/screens/bank_import.py)), and the reconciliation
    detail's head naming the statement and its account
    ([reconciliations.py](../../expense/tui/screens/reconciliations.py)), show `[like this]`
    whole in the app (the tester's check of 2026-10-27), but no test in
    [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) pins them.
13. **Two unit tests stop failing at random in CI.** Each fails now and then on one Python
    version and passes on the others, because it reads the screen before the screen has finished
    drawing: `test_config_screen_shows_only_the_engine_connection`
    ([test_tui_system.py](../../tests/unit/test_tui_system.py)) finds the `#card` text empty
    (`assert 'engine url' in ''`; CI runs 38196778409 on 2026-10-12, 38691759623 and 38810299743
    on 2026-10-15, 38853551793 on 2026-10-16), and
    `test_state8_a_partial_failure_ticks_what_landed`
    ([test_tui_log_bar.py](../../tests/unit/test_tui_log_bar.py)) raises
    `NoMatches("No nodes match '#field' on LogBarScreen()")` (runs 38595998705 on 2026-10-14,
    38860403478 on 2026-10-16). Each waits for what it reads, and whether the shared helpers in
    [helpers.py](../../tests/unit/helpers.py) (`wait_for_loaded`, `run_app`) should do that
    waiting for every test is checked.
14. **Two test docstrings say what is.** In
    [test_tui_reconciliations.py](../../tests/unit/test_tui_reconciliations.py) (around line
    226), "`date_start` orders the batch now" is said in the present tense, with no "now". In
    [test_tui_create_forms.py](../../tests/unit/test_tui_create_forms.py) (around line 409),
    "(the sheet import's, say)" goes: the import sends no colour, and the colour no swatch shows
    is the engine's own on a row created with none, as [tui.md](../tui.md) "Stepping past COLOR
    keeps it" says.
15. **A fixture quotes the engine's refusal to delete a sealed line.** `SEALED_LINE_WORDS` in
    test_tui_reconciliations.py reads "This bank line is in a completed reconciliation and cannot
    be deleted. …"; the engine sends "Cannot delete a bank line assigned to a completed
    reconciliation. Revert the reconciliation to draft first.", as
    [test_tui_delete.py](../../tests/unit/test_tui_delete.py) already has.
16. **The live import test names the stopping reconciliation through the app's own read.**
    `test_a_completed_reconciliation_stops_the_move_and_the_rest_imports` in
    [test_bank_import.py](../../tests/contract/test_bank_import.py) calls
    `GET /reconciliations/{id}` itself; it names it through `reconciliation_names`
    ([flow.py](../../expense/bank_import/flow.py)), so the app's path is proven live and not only
    mocked.
17. **A unit test pins that Reconciliations leaves out an archived account with no statement
    code.** The browse reads `GET /accounts` with `include_archived` and leaves archived accounts
    out of its list itself, so the whole card's list can name an archived card account's column
    ([reconciliations.py](../../expense/tui/screens/reconciliations.py)
    `ReconciliationsScreen.fetch`, [tui.md](../tui.md));
    `test_an_archived_card_accounts_halves_still_show_under_its_column` pins it for a card
    account only.
18. **The guard checks a test-engine start whole.** It allows a start from a subfolder of the
    engine checkout, since it checks the interpreter word `.venv/bin/python`, not that the
    command runs from the checkout's root; and it allows a start with only one of
    `SUPABASE_DB_URL` and `ADMIN_DB_URL`, though the engine coders' rule is both, every time
    ([guard.py](../../.claude/hooks/guard.py)). It requires both and checks the folder (or lists
    the folder under its docstring's limits), with tests in
    [test_claude_hooks.py](../../tests/unit/test_claude_hooks.py).

## How the owner knows it is done

1. The unit and live suites pass, and each point above has its test or its single copy.
2. The drift check against the practice engine is clean.

## Questions for the owner

None.
