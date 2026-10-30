# What the app's reads and writes catch-up turned up

Small things part 1 of the catch-up to contract `f82426fb0a099676`, the app's reads and writes on
an account and a currency (done on 2026-10-30), turned up while it ran.

**Status: draft, written 2026-10-30 for the owner to rewrite or approve, with two questions.**
Its tasks are drafted when the owner approves it. It runs after
[catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md), which redraws the
LOG bar and the account forms it touches; if spec 6 settles question 1's words or question 2's
CODE line on its own, that part leaves this spec. When done, the why moves to
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

## Questions for the owner

1. **What the LOG bar says when a name matches one account's two currencies** [mockup to draw].
   - **A.** Count currencies when they are one account's: `"$visa" matches 2 currencies of VISA
     Infinite Sapphire`, and the peek reads "of N in VISA Infinite Sapphire · USD".
   - **B.** Count what the picker shows, whatever it is: `"$visa" matches 2`, and the peek reads
     "of N in this currency".

   **Recommended:** A. It says why there are two and which account they belong to.
2. **Whether a person gets a statement code line.**
   - **A.** No: a statement code matches a bank's statement PDF, and a person has none; the forms
     stay as they are.
   - **B.** Yes: New and Edit account show CODE for a person too, as the engine allows.

   **Recommended:** A. A person has no bank statement to match, so the line would only invite a
   code nothing reads.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
