# Catch up to engine contract 8d2430081e64cd7c

**Status: current.** The owner approved the tasks on 2026-10-11.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The engine coders made five small changes on 2026-10-02 (the version check lists them in full
against 84321bd839912a09). None touches importing. The app keeps working against the engine
as it is now, and says so plainly where the engine now refuses something:

- **First-time setup with an empty name.** The engine now refuses a blank or spaces-only
  display name, at setup and on a profile change (contract: POST /v1/auth/bootstrap)
  (contract: PUT /v1/auth/profile). The app shows why instead of a bare error.
- **Exchange rates before setup.** For a user whose settings do not exist yet, the rate reads
  now answer `SETTINGS_MISSING` (contract: GET /v1/exchange-rates). The app points to
  first-time setup.
- **No `null` colour or order on a new account or person.** The engine refuses an explicit
  `null` on `color` or `sort_order` (contract: POST /v1/accounts) (contract: POST /v1/people).
  The app never sends one.
- **Batches stay at or under 500 rows** (contract: POST /v1/transactions/batch). The app sends
  200 at a time; a guard keeps it there.

Nothing the owner sees changes apart from the two clearer messages.

## How the owner knows it is done

1. The practice-engine check passes: the contract version matches and no fixture differs.
2. The live contract suite passes against the practice engine.

## Tasks

1. A guard that the batch chunk size stays at or under the engine's 500.
2. The first-time-setup hint for `SETTINGS_MISSING` lives once, in the shared error text, so the
   rate reads and every other command and screen show it; matched on the error code, never the
   wording.
3. The display name goes to the engine as typed: the TUI's first-time-setup prompt neither trims
   it nor drops a blank one, and the engine's `EMPTY` refusal is shown (first-time setup,
   profile), matched on the reason code, never the wording. Other prompts keep their behaviour.
4. With the practice engine up, settle two citations against the live contract: the transaction
   path written both `{id}` and `{transaction_id}` across the docs and code, and a citation for
   the calendar-day rule in [file-import-plan.md](../file-import-plan.md) §11.
