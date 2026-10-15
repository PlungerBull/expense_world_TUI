# Catch up with contract 42d70a629215928d

**Status: draft, deferred.** The loop does not start on it until the owner says so. The engine's
change note: [cli-answers/defaults-people-order-history-windows-ending-balance.md](../cli-answers/defaults-people-order-history-windows-ending-balance.md).
When done, the why moves to [decisions.md](../decisions.md), the change note is deleted, and this
file is deleted.

---

## What it must do

The app keeps working with the engine as it is after its changes of 2026-10-14 and 2026-10-15.

- **Completing a reconciliation needs its ending balance.** The engine now refuses to complete a
  reconciliation whose ending balance is empty (contract: POST /v1/reconciliations/{reconciliation_id}/complete).
  The owner chose (2026-10-15): when the owner completes a reconciliation that has no ending
  balance, the app **asks for it first**, saves it, then completes. A refusal that comes back
  anyway shows the engine's words plus a line saying what to do.
- **A new category does not need a colour.** The engine gives one when none is sent.
- **The account list keeps the engine's order**, real accounts first, then people.
- **The live contract tests follow the engine**: a reconciliation they complete has an ending
  balance, and the history reads page back with `previous_date_to`.

## How the owner knows it is done

1. Completing a reconciliation with no ending balance asks for it, then completes.
2. A new category saved without a colour comes back with the engine's default colour.
3. Every automated check passes, the live contract tests included.

## Open questions for the owner

Each is answered before its task starts.

- The screen that asks for the ending balance at complete is drawn for the owner to pick.
