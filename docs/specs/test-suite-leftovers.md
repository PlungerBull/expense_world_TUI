# Leftovers in the test suites

**Status: approved by the owner on 2026-10-28. It runs after the catch-up to contract
`f82426fb0a099676`
(part 1, the app's reads and writes (done on 2026-10-30) to
part 7 of the currencies catch-up (done on 2026-11-03)), which
rewrites many of the same files, and after
a month's statement closing from the bank's PDF (done on 2026-11-03). Its tasks are drafted
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
part 3 of the currencies catch-up, the live tests' foundation (done on 2026-10-30);
`_transaction_ids`, the create-into-a-statement test going and the import test naming its
stopping statement in
part 4 of the currencies catch-up, the live tests for the upload, bank lines and kinds (done on 2026-10-31);
the statement head shown whole in
part 7 of the currencies catch-up (done on 2026-11-03).
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
   part 1, the app's reads and writes (done on 2026-10-30), where
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
9. **Four unit tests stop failing at random in CI.** Each fails now and then on one Python version
   and passes on the others, and always passes on the owner's Mac, because it checks once, at a
   fixed moment, something the app finishes a moment later on GitHub's slower machines.
   `test_the_log_bars_batch_counts_as_one_save`
   ([test_tui_quit_asks.py](../../tests/unit/test_tui_quit_asks.py)) waits for the LOG bar's
   `_saving` to clear and then reads `pending_writes` once, but the save leaves that count only
   when its worker ends, just after (`assert [1, …, 1] == [1, …, 0]`; nearly every run from
   42310670430 on 2026-11-06 to 42380381276 on 2026-11-07, on all three Python versions), and
   `test_a_wrapped_head_costs_the_checklist_a_row_and_nothing_overflows[24]`
   ([test_tui_statement_screen.py](../../tests/unit/test_tui_statement_screen.py)) checks the
   list fits `#rlist` after two fixed pauses, before the list is measured again under the drawn
   head (`assert fits`; runs 42314220786 on 2026-11-06, 42380267554 on 2026-11-07). Each waits
   until what it checks is so, and still fails when it never becomes so. The other two read the
   screen before it has finished drawing:
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

Item 5 needs no task: test_errors.py's refusal-row comments already say what their rows prove.
Item 3 is nearly done: the live suite keeps one copy of `refused` and `refused_writing_nothing`
in its conftest.py, and `_safe_delete` lives in one file only; what is left of it (each file's
own "refused, and this read the same before and after" step) goes with item 7 in task 5.

5. **One shared "refused, nothing changed" step in the live suite (items 3's rest, and 7).**
   One step in tests/contract/conftest.py takes a read and a call, and gives the refusal with
   the read the same before and after; test_bank_line_write.py's hand-written refused-then-read
   and `_refused_unwritten` in test_bank_line_edit_limits.py use it, as do the other files'
   own versions of that step where it fits.
6. **The bank import's heads pinned with a bracketed name (item 8).**
   test_tui_bracketed_names.py proves the bank import's account list and its
   `Preview · <account>` head show `[like this]` whole.
7. **Two CI-flaky tests wait until what they check is so (item 9, first pair).**
   `test_the_log_bars_batch_counts_as_one_save` and
   `test_a_wrapped_head_costs_the_checklist_a_row_and_nothing_overflows[24]` wait for the state
   they check, and still fail when it never comes.
8. **Two CI-flaky tests wait for the screen to finish drawing (item 9, second pair).**
   `test_config_screen_shows_only_the_engine_connection` and
   `test_state8_a_partial_failure_ticks_what_landed` wait for what they read; the builder checks
   whether `wait_for_loaded` or `run_app` should do that waiting for every test and reports what
   it found, changing them only if that change is small and keeps the suite green.

## Found along the way

- The drift check reads a nested union wrongly: for an answer `anyOf [X, anyOf [Y, Z]]` it
  checks against X alone, and for `anyOf [anyOf [Y, Z]]` it says the contract holds no JSON
  answer, where both should say the answer comes in more than one shape (`_object_schema`
  and `answered_in_many_shapes` in scripts/check_fixture_drift.py). No marked endpoint has
  such an answer today.
- The drift check reads a field passed by name only to a `**fields` builder in
  tests/unit/helpers.py; the `**fields` builders local to one test file (`_kept`, `_statement`,
  …) are not read, and nothing says so.
- tests/unit/test_no_read_only_fields.py writes the engine address and token itself (lines
  174, 187, 231) where `ENGINE_URL` and `ENGINE_TOKEN` in helpers.py hold them.
