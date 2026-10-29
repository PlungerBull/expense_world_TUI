# Leftovers of the bank download and closing catch-up

**Status: approved by the owner on 2026-10-28; no question open. It runs after the
catch-up to contract `e7393dd869963db1` (the catch-up's specs named below), which touches the same
files. Its tasks are drafted when the owner names it the current spec.** When done, the why moves
to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Found while the catch-up of the engine's hand-off of 2026-10-26 sent bank downloads whole, showed
what a statement's close flags and took a card's other account from the engine (done on
2026-10-26), and while the sheet import went through the engine (2026-10-27), not fixed there.
None of it changes what you see; it is code, tests and drawings that say old things.

The rest of what this spec held on 2026-10-26 moved into the catch-up to `e7393dd869963db1`,
which rewrites the same code: the engine's old words, the "no batch" helper's names and comment,
and the grouped refusals' drawing into
part 1b, the statement screens (done on 2026-10-28); the practice-data
cleaner into
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md); a
completed statement's footer, the "no batch" list's order and the card statement's drawing, with
both their questions, into
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).
The point about the ids read's bound is dropped: the engine itself states that bound as the
list's largest page (contract: GET /v1/bank-lines, "At most 200 ids").

## What it must do

1. **The held-reserved-name live test builds its download through the shared helpers.**
   [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) builds its
   download's header and body by hand, where the contract conftest's shared `download_body` and
   `CURRENT_HEADER` do it ([conftest.py](../../tests/contract/conftest.py)).
2. **The batch helper keeps only what a caller uses.** `chunk_size`,
   `require_sendable_chunk_size` and the `engine_text` default in
   [batch_write.py](../../expense/batch_write.py) serve no caller but the tests, since the LOG bar
   always passes its own; and a test docstring in
   [test_batch_write.py](../../tests/unit/test_batch_write.py) calls the default "the
   importer's".
3. **Stale comments and tags say plainly what they mean.** The comment above `_ENVELOPE_ERRORS`
   in [errors.py](../../expense/errors.py) says EngineError is a branch in `render()`, where it is
   in `json_body` and `exit_code_of`. Two comments in
   [import_cmd.py](../../expense/commands/import_cmd.py) carry "pick 2 A" tags instead of saying
   what they mean. [test_tui_setup.py](../../tests/unit/test_tui_setup.py) keeps the old
   "openpyxl is required for `expense import`" words as a guard's fixture text.
4. **Four mockups draw the words the app shows**, or are deleted with their links if they back
   no open work (the rule in [todo.md](../todo.md) "Mockups that back no open work"), in
   [mockups/](../mockups/):
   - `expense-world-split-transaction-screen.html`: a part's amount stating both totals;
   - `expense-world-edit-part.html`: "Another part of this bank line …";
   - `expense-world-import-door.html`: "not a BCP bank file", and a movement count on its account
     list (if the catch-up redraws the account list for cards, this drawing goes with it there);
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
