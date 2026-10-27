# Leftovers of the engine's words: lists that keep them, and tests that prove them

**Status: approved, the current spec while
[sheet-import-through-the-engine.md](sheet-import-through-the-engine.md) waits on the engine
(owner, 2026-10-26).** When done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## Why

Found while the notes spec made every note show the engine's words whole and the Edit form say
why a line is read-only (done on 2026-10-26), not fixed there:

- **Lists still lose bracketed text.** A name or title the engine holds that contains
  `[like this]` loses it in a list: an account named `BCP [like this]` shows as `BCP `. Every list
  reads its cells as styling ([cursor_list.py](../../expense/tui/widgets/cursor_list.py) `_cell`),
  and so does the bank import preview's title
  ([bank_import.py](../../expense/tui/screens/bank_import.py)).
- **The bulk edit's note can lose a backslash.** Engine words ending in `\` lose one when the
  app's own styling closes straight after them (`refusal_notes` in
  [transactions.py](../../expense/tui/screens/transactions.py); the limit is written in
  `as_markup`'s docstring in [refusal.py](../../expense/tui/widgets/refusal.py)).
- **Some tests prove less than they say:**
  - The live `edit_limits` test never reads a refused write back: its docstring says every
    refusal writes nothing, but the writes refused on locked fields are checked only by their
    refusal ([test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py)).
  - Nothing checks the unit fake engine's six lock sentences (`LOCK_MESSAGES` in
    [helpers.py](../../tests/unit/helpers.py)) against the live contract; the drift check
    compares keys, not values.
  - Toasts of the owner's own typing (`No account matches "…"`, `Nothing matches "…"`, System's
    invalid-URL and config-save toasts) show it as text, but no test types `[like this]` into
    them.
  - No bulk-edit test pins `N of M refused` when two or more rows are refused for their own
    reason before missing settings stop the run, and the mid-run stop's test checks the
    selection alone, not the receipt, the `Failed` note, or that no `Refused` note shows
    ([test_tui_bulk_edit.py](../../tests/unit/test_tui_bulk_edit.py)).
- **Small things in the tests:**
  - The test helper `toasts_shown` reads Textual's private `Toast` class
    ([helpers.py](../../tests/unit/helpers.py)); a Textual upgrade could move it.
  - The `readonly_lines` test writes the parts table's column words as keywords
    (`dict(amount=…)`) so the drift check, which reads quoted keys only, does not take them for
    engine fields; nothing in the test says so
    ([test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py)).
  - The docstring of
    [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py)
    says completing locks "amount/account/title/date"; the engine locks six things: amount,
    date, title, account, operation number and reconciliation.
- **Two mockups still draw the old complete question**: `expense-world-split-transaction-screen.html`
  and `expense-world-card-statement.html` in [mockups/](../mockups/).

## What it must do

1. **Every name and title in a list shows as the engine holds it**, `[` and all, never read as
   styling, in every list and in the bank import preview.
2. **The bulk edit's note shows engine words ending in a backslash whole.**
3. **The tests prove what they say**: the live `edit_limits` test reads each refused write back
   and finds it unwritten; a check fails when the unit fake engine's lock sentences differ from
   the live contract's; the owner's own typing with `[like this]` shows whole in each of its
   toasts; the bulk edit's stop note is pinned with several refused rows and in a mid-run stop.
4. **The small things are tidied**: the toast helper reads no private Textual class, or says why
   it must; the keyword-written test says why; the lifecycle test's docstring names the six
   locked things; the two mockups draw the question as the app asks it.

## How the owner knows it is done

1. An account named `BCP [like this]` shows its whole name in Manage ▸ Accounts and in every
   list naming it.
2. The unit suite, the live suite and the drift check pass.

## Questions for the owner

None. Nothing you see changes but the bracketed names, which now show whole.

---

## Tasks

Approved by the owner on 2026-10-26.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **Another live file reads a refused write back by hand.**
  [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py) (around lines 233 and
  293) writes the refused-then-unchanged read that `_refused_unwritten` in
  test_bank_line_edit_limits.py now does; one shared step in the contract conftest. (Task 4.)
- **A mockup draws an old revert question.** The "u · the question" pane of
  `expense-world-card-statement.html` in [mockups/](../mockups/) reads "Unlocks their
  transactions and balances. The order stays."; the app asks "Unlocks the assigned transactions
  and this batch's balances." ([reconciliations.py](../../expense/tui/screens/reconciliations.py)).
  (Task 6.)
