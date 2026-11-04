# What the app's reads and writes catch-up turned up

Small things part 1 of the catch-up to contract `f82426fb0a099676`, the app's reads and writes on
an account and a currency (done on 2026-10-30), turned up while it ran.

**Status: both questions answered and the three tasks approved by the owner on
2026-11-03.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **The LOG bar counts accounts where it means currencies.** `$visa` on the Visa holding soles
  and dollars says `"$visa" matches 2 accounts` on the hint line and in a refused row's note,
  though it is one account offering its two currencies; and the peek under the bar reads
  "of N in this account" while it lists one currency of the account.
- **A person may hold a statement code, and the forms offer none.** The engine judges a
  person's statement code by the same rules as a bank account's
  (contract: POST /v1/accounts, "Optional"), but the New and Edit account forms show no CODE line
  for a person, so no screen can give one or read one back.
- **The LOG bar's unit tests name their accounts the old way.** Accounts such as "BCP
  Signature PEN" now read "BCP Signature PEN · PEN" in the tests, a currency named twice; the
  tests should use account names that hold currencies, as the engine has them now.
- **Two code comments describe what is no longer so:** the Manage ▸ Accounts module comment says
  the Code column is `—` for a person always, though the engine lets a person carry a code
  (contract: "What an account is", "A person carries a code like any account"), and the ledger's
  bulk-move comment shows a receipt in the old naming (`3 rows → BCP USD · …`) where the app
  shows the pick's label.

## What it must do

1. **The LOG bar's words say what was matched:** the hint, a refused row's note and the peek's
   count read as question 1 decides.
2. **A person's statement code** is offered or not as question 2 decides.
3. **The LOG bar's unit tests** name their accounts as accounts holding currencies, with no
   currency in an account's name.
4. **The two code comments** say what the code does.

## How the owner knows it is done

1. On the practice engine, `$visa` on the Visa holding soles and dollars says what question 1
   picked, on the hint and in a refused row, and the peek on the Visa's dollars counts as
   question 1 picked.
2. A person is created and edited with or without a statement code, as question 2 picked.
3. The unit suite and the drift check pass.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | What the LOG bar says when a name matches one account's two currencies? [expense-world-leftover-picks.html](../mockups/expense-world-leftover-picks.html) pane 1 | A: the peek's count names the account and its currency, `3 of 48 in VISA Infinite Sapphire · USD · newest first`. The hint's half is settled already: since part 6, `$visa` matches the Visa once, so no hint counts its currencies as accounts (2026-11-03). |
| 2 | Whether a person gets a statement code line? | A: no; the New and Edit forms stay as they are for a person (2026-11-03). |

---

## Tasks

Approved by the owner on 2026-11-03.

3. **The two code comments say what the code does** (What it must do 4): the module docstring
   of [accounts.py](../../expense/tui/screens/accounts.py) (a person's Code is its statement
   code like any account's, `—` when it has none) and the bulk-write receipt's docstring in
   [transactions.py](../../expense/tui/screens/transactions.py) (the pick's label, not
   `BCP USD`).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **A long account name wraps the peek's count line.** The count is one line in the panel's
  sizing, but at 80 columns a pick label over about 40 letters (`1716 of 1716 in <long name> ·
  PEN · newest first`) wraps to two, and the panel clips the second. Seen in review of task 1
  (2026-11-03), in [log_bar.py](../../expense/tui/screens/log_bar.py) `AccountPeek`.
- **About 20 other unit test files still name accounts with a currency code** (`BCP Signature
  PEN`, `BCP PEN`, `BCP USD`): among them `test_tui_engine_words.py`,
  `test_tui_bracketed_names.py`, `test_tui_dropped.py` and `test_tui_flagged_lines.py`
  (`grep -rln 'BCP PEN\|BCP Signature PEN\|BCP USD' tests/unit`). Seen in review of task 2
  (2026-11-03). Nothing you see changes.
