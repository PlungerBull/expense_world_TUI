# Leftovers in the test suites

**Status: approved by the owner on 2026-10-28. It runs after the catch-up to contract
`f82426fb0a099676`
([catch-up-currencies-1-reads-and-writes.md](catch-up-currencies-1-reads-and-writes.md) to
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)), which
rewrites many of the same files, and after
[statements-close-from-their-pdf.md](statements-close-from-their-pdf.md). Its tasks are drafted
when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Small things found while doing the statement catch-up's leftovers (2026-10-25), while proving a
held reserved name on the Edit form (2026-10-25) and while making lists show bracketed names
whole (2026-10-27), not fixed there; and the backlog's items that live only in the tests and
their tools, brought in by the owner on 2026-10-27. All of them are inside the test suites and
their tools: nothing you see changes, and no engine change is needed.

The points on code a catch-up rewrites live in that catch-up: one account-record builder for
the unit suite, the coverage-gap warning fixture, the sealed line's delete words and two test
comments on statements and people in the cards and statements catch-up's parts 1a and 1b
(done on 2026-10-28); the contract files building their records through `Scratch`, the
statement-order helper going and the practice-user cleaner (reading every page among its
rework) in
[catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md);
`_transaction_ids`, the create-into-a-statement test going and the import test naming its
stopping statement in
[catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md);
the statement head shown whole in
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).
The points on things the engine no longer has are dropped: a card statement's create answer
built by hand, a card's other half checked against its own schema, a reconciliation create's
builders, a test docstring on the one-account create form, the browse leaving out an archived
account with no code (an account is archived whole). So is the guard's check of a hand start
of the test engine: the guard blocks a hand start and allows only the engine's own launcher.

## What it must do

1. **The drift check covers more answers**: the update's answer builder (`put_answer`) and a bank
   line's read (`bank_line_row`) in [helpers.py](../../tests/unit/helpers.py) carry
   `@answer_of` too, beside the statement builders the catch-up marks; a marked answer's extra
   keys are checked against its own endpoint; `answer_of` refuses a second builder for one
   endpoint; and an answer the contract allows in more than one shape (`GET /v1/reports/monthly`
   today) is named as such, not as "no JSON answer"
   ([the drift script](../../scripts/check_fixture_drift.py)). It runs after
   [catch-up-currencies-1-reads-and-writes.md](catch-up-currencies-1-reads-and-writes.md), where
   `bank_line_row` gains `account_id` and `currency_code`.
2. **`stub_home_month` says what it replaces**: in helpers.py it also replaces the settings with a
   bare object, so a respx test that calls it fails on `engine_url`; its name or docstring says
   so, or it stops doing it.
3. **One copy of `_safe` and `_refused` in the live suite**: defined again in about 20 files in
   [tests/contract/](../../tests/contract/) (`_safe`, `_safe_delete` or `_safe_post`, and
   `_refused`), they have one copy in [conftest.py](../../tests/contract/conftest.py) beside
   `client`, `reason_on` and `statuses`.
4. **The drift script's docstring points to runtime.md** instead of repeating it: its REQUIRED
   FIELDS and KNOWN LIMITATION blocks copy [runtime.md](../runtime.md) "Fixture drift", where its
   CONTRACT VERSION block already just links there; its example of an answer the check cannot see
   names a `coverage_gap` only.
5. **Two test comments say what their rows prove.** In
   [test_errors.py](../../tests/unit/test_errors.py), the comments heading the refusal rows say
   "pending-hashtag-manage 4 B, both refusals, and 5 B" and "pending-hashtag-manage 7 B"; each
   says what its rows prove instead.
6. **The Edit form's shared hashtag-refusal test checks what it says.**
   `test_a_hashtag_refusal_shows_under_the_parts_as_sent` in
   [test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py) runs every hashtag refusal,
   `RESERVED_NAME_HELD` among them, but when a reason has no line of the app's it checks nothing,
   so it would pass with one showing. It proves no line of the app's shows for those reasons, and
   for every reason that "Nothing was saved." shows and one write was sent.
7. **One shared step reads a refused write back in the live suite.**
   [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py) writes by hand the
   refused-then-unchanged read that `_refused_unwritten` in
   [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) does; one
   shared step in the contract [conftest.py](../../tests/contract/conftest.py) serves both.
8. **The bank import's heads are pinned showing a bracketed name whole.** The bank import's
   account list (`account_lines`) and its `Preview · <account>` head
   ([bank_import.py](../../expense/tui/screens/bank_import.py)) show `[like this]` whole in the
   app (the tester's check of 2026-10-27), but no test in
   [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) pins them.
9. **Two unit tests stop failing at random in CI.** Each fails now and then on one Python version
   and passes on the others, because it reads the screen before the screen has finished drawing:
   `test_config_screen_shows_only_the_engine_connection`
   ([test_tui_system.py](../../tests/unit/test_tui_system.py)) finds the `#card` text empty
   (`assert 'engine url' in ''`; CI runs 38196778409 on 2026-10-12, 38691759623 and 38810299743
   on 2026-10-15, 38853551793 on 2026-10-16), and
   `test_state8_a_partial_failure_ticks_what_landed`
   ([test_tui_log_bar.py](../../tests/unit/test_tui_log_bar.py)) raises
   `NoMatches("No nodes match '#field' on LogBarScreen()")` (runs 38595998705 on 2026-10-14,
   38860403478 on 2026-10-16). Each waits for what it reads, and whether the shared helpers in
   [helpers.py](../../tests/unit/helpers.py) (`wait_for_loaded`, `run_app`) should do that
   waiting for every test is checked.
10. **A test docstring says what is.** In
    [test_tui_create_forms.py](../../tests/unit/test_tui_create_forms.py) (around line 409),
    "(the sheet import's, say)" goes: the import sends no colour, and the colour no swatch shows
    is the engine's own on a row created with none, as [tui.md](../tui.md) "Stepping past COLOR
    keeps it" says.
11. **The drift check reads a key a test passes to an answer builder by name.** It reads a
    fixture's keys only when written as a quoted `"key":`, so a key a test passes to a builder
    in [helpers.py](../../tests/unit/helpers.py) by name (`statement_partner_id=…`) is never
    checked against the contract, and an old field can hide there
    ([the drift script](../../scripts/check_fixture_drift.py)). It reads such keys and names one
    the contract lacks; a unit test proves it names a made-up field passed by name.

## How the owner knows it is done

1. The unit and live suites pass, and each point above has its test or its single copy.
2. The drift check against the practice engine is clean.

## Questions for the owner

None.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way
