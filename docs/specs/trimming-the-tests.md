# Trimming the tests

**Status: approved on 2026-11-09.** It runs right after the catch-up, while the leftover-lines
spec waits on the engine. When done, the why
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

1. The summary at the end gives the test code's lines, the number of tests and the whole unit
   suite's time before and after, counted the way this spec's Why counts them, and what a
   further cut would take, for the owner to decide whether to cut more.
2. The app's code coverage is within 2 points of the baseline below.
3. The tester runs the live contract suite green and opens the app: every screen works as
   before.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | How far to cut? | C: as far as the rule goes, with no target; the numbers are reported at the end, and the owner then decides whether to cut more (2026-11-09). |

---

## Tasks

**The baseline, 2026-11-09:** the app 22,306 lines; the tests 76,354 lines (tests/unit 59,839,
tests/contract 16,475), 4,524 unit tests and 416 live ones; the whole unit suite 109 seconds on
an idle Mac; the app's code coverage 98% (235 of 10,200 statements not run).

Approved. Each task cuts by the rule, keeps `pytest tests/unit` green, and reports
lines and tests before and after; its reviewer confirms that each behaviour a cut test proved
is proven by a test that stays, or is nothing the owner would notice. The test items the Backlog held
(the small test cleanups from the catch-up to `1002f105c6bacdf1`, from the account numbers work
and from the number format, "No list test renders an engine-sent total past the largest
amount", and dashboard rows built by hand without `kind` in test_tui_bracketed_names.py,
test_tui_home_dispatch.py and test_tui_home_header.py, with test_tui_smoke.py's sample rows in
an old flat shape) join the task whose files they touch, done there or dropped by the rule.

7. **The rest of tests/unit,** test_tui_help.py and test_tui_quit_asks.py first (and
   `fake_ledger`'s unprompted `offset` refusal in helpers.py with test_reads_and_formatting.py), then the live
   suite's repeated cases in tests/contract.
8. **The speed:** the slowest tests left made fast or merged; helpers no test uses any more
   (`_cine_line` in test_tui_delete.py, `_enter` in test_tui_new_account.py) and the
   source-reading `test_a_forms_own_enter_handler_stops_the_ones_under_it` in
   test_tui_create_forms.py, whose double write real presses already prove, removed; the tests gate's wait in .claude/hooks/tests_gate.py brought down to fit; the doc
   lines on test conventions (docs/tui.md, docs/runtime.md) cut to the rule.

## Found along the way

Not built in this spec; sorted when it is done.

- **`written()` in `t`'s question repeats `_currency_write`** (expense/tui/screens/accounts.py:317,
  :382): two copies of one write's body in the app code.
