# Catch up with contract 42d70a629215928d

**Status: draft, deferred.** The loop does not start on it until the owner says so. The engine's
change note: [engine-answers/defaults-people-order-history-windows-ending-balance.md](../engine-answers/defaults-people-order-history-windows-ending-balance.md).
When done, the why moves to [decisions.md](../decisions.md), the change note is deleted, and this
file is deleted.

This spec ships before [official-migration.md](official-migration.md): that spec completes the
2026 reconciliations, which needs the ending-balance flow below.

---

## What it must do

The app keeps working with the engine as it is after its changes of 2026-10-14 and 2026-10-15.

- **Completing a reconciliation needs its ending balance.** The engine now refuses to complete a
  reconciliation whose ending balance is empty (contract: POST /v1/reconciliations/{reconciliation_id}/complete).
  The owner chose (2026-10-15): when the owner completes a reconciliation that has no ending
  balance, the app **asks for it first**, saves it, then completes. A refusal that comes back
  anyway shows the engine's words plus a line saying what to do. No reconciliation is already
  completed without an ending balance, so the app offers no fix for that case.
- **A new category does not need a colour.** The New Category form makes colour optional, the
  way the New Account form already is, and the engine gives one when none is sent. The sheet
  import sends no colour for the categories it creates, so they take the engine's default blue
  (owner, 2026-10-15).
- **The account list keeps the engine's order**, real accounts first, then people.
- **The live contract tests follow the engine:**
  - a reconciliation they complete has an ending balance, and completing one without it is
    refused;
  - a category and an account created without a colour come back with the engine's default
    colour;
  - the account list with people lists every real account before every person;
  - activity history and exchange-rate history page back with `previous_date_to` and never read
    a row twice. Exchange-rate history gets its first live test; no screen reads it, so this
    suite is the only client that exercises it. Its 366-day limit and its refusal of a date the
    calendar cannot hold are tested too.

## How the owner knows it is done

1. Completing a reconciliation with no ending balance asks for it, then completes.
2. A new category saved without a colour comes back with the engine's default colour, and so
   does a new account.
3. Every automated check passes, the live contract tests included.
4. [docs/engine-answers/](../engine-answers/) holds no note this client has caught up with.

## Open questions for the owner

Each is answered before its task starts.

- How the app asks for the ending balance at complete: A (ask for the balance, then the usual
  complete question) or B (one box that saves the balance and completes). Drawn in
  [mockups/expense-world-ending-balance-and-category-colour.html](../mockups/expense-world-ending-balance-and-category-colour.html), Part 1.
- The New Category form with an optional colour: same mockup, Part 2.
- The owner tells the engine coders the client has caught up with the refusal reasons.
