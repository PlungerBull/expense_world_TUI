# Leftovers in the test suites

**Status: approved by the owner on 2026-10-28; on 2026-10-27 the owner brought in the
test-only items of todo.md's backlog. It runs after the catch-up to contract
`e7393dd869963db1` (the catch-up's specs named below), which rewrites many of the same files. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Small things found while doing the statement catch-up's leftovers (2026-10-25), while proving a
held reserved name on the Edit form (2026-10-25) and while making lists show bracketed names
whole (2026-10-27), not fixed there; and the backlog's items that live only in the tests and
their tools, brought in by the owner on 2026-10-27. All of them are inside the test suites and
their tools: nothing you see changes, and no engine change is needed.

The points on code the catch-up to `e7393dd869963db1` rewrites moved into it: one account-record
builder for the unit suite, the coverage-gap warning fixture, the sealed line's delete words and
two test comments on statements and people into
part 1a, the app's reads and writes (done on 2026-10-28) and
part 1b, the statement screens (done on 2026-10-28); the contract
files building their records through `Scratch`, `_transaction_ids`, the statement-order helper
and the create-into-a-statement test going, the practice-user cleaner (reading every page among
its rework) and the import test naming
its stopping statement into
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md) and
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md); the
statement head shown whole into
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).
The points on things the engine no longer has are dropped: a card statement's create answer
built by hand, a card's other half checked against its own schema, a reconciliation create's
builders, a test docstring on the one-account create form, and the browse leaving out an
archived account with no code (a holder's accounts are archived together now).

## What it must do

1. **The drift check covers more answers**: the update's answer builder (`put_answer`) and a bank
   line's read (`bank_line_row`) in [helpers.py](../../tests/unit/helpers.py) carry
   `@answer_of` too, beside the statement builders the catch-up marks; a marked answer's extra
   keys are checked against its own endpoint; `answer_of` refuses a second builder for one
   endpoint; and an answer the contract allows in more than one shape (`GET /v1/reports/monthly`
   today) is named as such, not as "no JSON answer"
   ([the drift script](../../scripts/check_fixture_drift.py)).
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
11. **The guard checks a test-engine start whole.** It allows a start from a subfolder of the
    engine checkout, since it checks the interpreter word `.venv/bin/python`, not that the command
    runs from the checkout's root; and it allows a start with only one of `SUPABASE_DB_URL` and
    `ADMIN_DB_URL`, though the engine coders' rule is both, every time
    ([guard.py](../../.claude/hooks/guard.py)). It requires both and checks the folder (or lists
    the folder under its docstring's limits), with tests in
    [test_claude_hooks.py](../../tests/unit/test_claude_hooks.py).

## How the owner knows it is done

1. The unit and live suites pass, and each point above has its test or its single copy.
2. The drift check against the practice engine is clean.

## Questions for the owner

None.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way
