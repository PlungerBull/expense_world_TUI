# Trimming the tests

**Status: draft for the owner to approve, 2026-11-09. Its questions are below, with its tasks
drafted on the recommended answers; one reply answers them and approves it.** It runs right
after the catch-up, while the leftover-lines spec waits on the engine. When done, the why
moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The tests have outgrown the app. On 2026-11-09 the app is 22,300 lines of code and its tests
76,300 lines, 4,521 unit tests and 416 live ones: over three lines of test per line of app.
openGym, a well-tested app of the same kind, has about one; Firefly III far less. The whole
unit suite runs 109 seconds on an idle Mac and past four minutes on a busy one, and every
commit waits for it. Much of the weight proves the same thing twice, re-states engine rules
the live suite already judges, or checks other tests.

The rule that grew it is changed ([CLAUDE.md](../../CLAUDE.md) "Testing conventions",
[decisions.md](../decisions.md) "Tests prove what the owner would notice, once"). This spec
brings the tests already written under that rule.

## What it must do

1. **Every test that stays proves something the owner would notice,** once. A behaviour proven
   twice keeps one test; refusals shown the shared way keep one test of the shared code.
2. **No unit test re-states an engine rule;** fakes answer what each test sets up.
3. **Tests that check other tests go,** but for those that keep the real ledger and keys safe
   (the agents' guard) and those that keep docs from misleading (dead links, wrong citations).
4. **Nothing the app does changes,** and nothing the owner would notice is left unproven.

## How the owner knows it is done

1. The test code is at most 1.5 times the app's code, counted the way this spec's Why counts it.
2. The whole unit suite runs in under 60 seconds on an idle Mac.
3. The app's code coverage is within 2 points of what task 1 measures before cutting.
4. The tester runs the live contract suite green and opens the app: every screen works as
   before.

## Open questions

1. **How far to cut.**
   - **A.** Lean: test code at most 1.5 times the app's (about 33,000 lines, under half of
     today's), the unit suite under 60 seconds.
   - **B.** Moderate: at most 2 times (about 45,000 lines), under 80 seconds.
   - **C.** No numbers: apply the rule and take whatever it gives.
   - **Recommended:** A, close to what openGym runs, and a number the reviewer can check.

---

## Tasks

Drafted on answer A. Each task cuts by the rule, keeps `pytest tests/unit` green, and reports
lines and tests before and after; its reviewer confirms that each behaviour a cut test proved
is proven by a test that stays, or is nothing the owner would notice. The Backlog's test items
(the small test cleanups from the catch-up to `1002f105c6bacdf1`, from the account numbers work
and from the number format, and "No list test renders an engine-sent total past the largest
amount") leave the Backlog when this spec is approved and join the task whose files they
touch, done there or dropped by the rule.

1. **The baseline and the engine-rule copies:** record coverage, lines and suite time; drop the
   unit tests' copies of engine rules (the autouse read-only-field refusal in
   tests/unit/conftest.py and `helpers.refuse_read_only_fields`, fakes refusing what no test
   asks them to) and the tests that check them in test_suite_hygiene.py.
2. **The tests about tests:** test_suite_hygiene.py, test_shared_code_home.py,
   test_parallel_runs.py and test_doc_hygiene.py keep only what point 3 of "What it must do"
   keeps; test_claude_hooks.py loses repeated cases, never a rule it trips.
3. **The LOG bar:** test_tui_log_bar.py and the quick-add parser's tests, one test per
   behaviour, near-copies merged into one table of cases.
4. **The statements:** test_tui_statements.py, test_tui_statement_detail.py,
   test_tui_statement_upload.py, test_tui_statement_balances.py, test_tui_flagged_lines.py,
   test_tui_flagged_panes.py and test_tui_bank_import.py.
5. **The edit forms:** test_tui_edit_form.py, test_tui_edit_form_parts.py,
   test_tui_bulk_edit.py and test_tui_form_hints.py.
6. **Accounts and the other forms:** test_tui_opening_balance.py, test_tui_create_forms.py,
   test_tui_delete.py, test_tui_statement_code.py and the account tests.
7. **The rest of tests/unit,** test_tui_help.py and test_tui_quit_asks.py first, then the live
   suite's repeated cases in tests/contract.
8. **The speed:** the slowest tests left made fast or merged until the suite is under 60
   seconds; the tests gate's wait in .claude/hooks/tests_gate.py brought down to fit; the doc
   lines on test conventions (docs/tui.md, docs/runtime.md) cut to the rule.

## Found along the way

Not built in this spec; sorted when it is done.
