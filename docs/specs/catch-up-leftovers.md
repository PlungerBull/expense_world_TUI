# Leftovers of the bank download and closing catch-up

**Status: approved by the owner on 2026-10-28; no question open. It runs after the catch-up to
contract `f82426fb0a099676`
(1 (done on 2026-10-30), 2 (done on 2026-10-30),
3 (done on 2026-10-30), [4](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
[5](catch-up-currencies-5-live-suite-account-currencies.md), [6](catch-up-currencies-6-main-views.md),
[7](catch-up-currencies-7-statement-screen.md)), which rewrites the same files. Its tasks are drafted when the owner names it the current spec.** When done, the why
moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Found in the code that sends bank downloads whole, shows what a statement's close flags and runs
the sheet import through the engine, and not fixed there. None of it changes what you see; it is
code, tests and drawings that say old things.

The rest of what was found belongs to other specs: the practice-data cleaner to
part 3 of the currencies catch-up, the live suite's foundation (done on 2026-10-30), which moved
the cleaner to the new model; a completed statement's
footer, the "no batch" list's order and the card statement's drawing, with both their questions,
to [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md); the
import door's account list, with its drawing `expense-world-import-door.html` ("not a BCP bank
file", and a movement count on its account list), to
[catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md). The ids read's bound
needs no point: the engine itself states that bound as the list's largest page
(contract: GET /v1/bank-lines, "At most 200 ids").

## What it must do

1. **The held-reserved-name live test builds its download through the shared helpers.**
   [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) builds its
   download's header and body by hand, where the contract conftest's shared `download_body` and
   `CURRENT_HEADER` do it ([conftest.py](../../tests/contract/conftest.py)). The app's download is on
   the new model since part 2 of the currencies catch-up (done on 2026-10-30): a download names only the account, each row going to the currency in its own `Moneda`
   (contract: POST /v1/transactions/import, "Accounts").
2. **The batch helper keeps only what a caller uses.** `chunk_size`,
   `require_sendable_chunk_size` and the `engine_text` default in
   [batch_write.py](../../expense/batch_write.py) serve no caller but the tests, since the LOG bar
   always passes its own; and a test docstring in
   [test_batch_write.py](../../tests/unit/test_batch_write.py) calls the default "the
   importer's". Each item's `currency_code` in the same file is
   part 1, the app's reads and writes (done on 2026-10-30)'s.
3. **Stale comments and tags say plainly what they mean.** The comment above `_ENVELOPE_ERRORS`
   in [errors.py](../../expense/errors.py) says EngineError is a branch in `render()`, where it is
   in `json_body` and `exit_code_of`. Two comments in
   [import_cmd.py](../../expense/commands/import_cmd.py) carry "pick 2 A" tags instead of saying
   what they mean. [test_tui_setup.py](../../tests/unit/test_tui_setup.py) keeps the old
   "openpyxl is required for `expense import`" words as a guard's fixture text.
4. **Three mockups draw the words the app shows**, or are deleted with their links if they back
   no open work (the rule in [todo.md](../todo.md) "Mockups that back no open work"), in
   [mockups/](../mockups/):
   - `expense-world-split-transaction-screen.html`: a part's amount stating both totals;
   - `expense-world-edit-part.html`: "Another part of this bank line …";
   - `expense-world-import-report.html`: the `Before 2026` and `Couldn't read the row` rows the
     app no longer shows.

## How the owner knows it is done

1. Nothing you see changes.
2. The unit suite, the live suite and the drift check pass.

## Questions for the owner

None.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
