# Catch up with the contract's trimmed and corrected wording

**Status: approved, 2026-10-18.** The loop runs its tasks.
**Catches up to contract `15063ec5587491ad`:** every contract change after `c4327854a6d6e301`.
It holds the engine's hand-off "The contract's wording was trimmed and corrected; no behaviour
changed". What it asks of this client is in the tasks, and its checks are in "The engine's
checks". When done, the why moves to [decisions.md](../decisions.md), and this file is deleted.

---

## What it must do

**Clearing a transaction's note on the Edit form saves.** Today the form sends an emptied note
in a way the engine refuses, so the owner sees a refusal instead of `Saved.`. With this spec the
note is emptied and the form says `Saved.`, as for any other change. Nothing on screen changes.

**A transaction on an archived account stays editable.** Changing its category, hashtags or
note, splitting it and deleting it all work. Moving it to another account works; the app never
offers an archived account to move a transaction onto.

**Every place the app's code and docs point into the contract still points at the right
part.** The engine moved several rules to new places and renamed some; nothing the owner sees
changes.

## How the owner knows it is done

1. On the Edit form, clearing a transaction's note and saving says `Saved.`, and the note is
   gone from the transaction.
2. On a transaction whose account is archived, changing its category, splitting it and deleting
   it each go through.

## The engine's checks

The engine's own "Done when" for this range. The tester's acceptance check runs them, and the
reply to the engine reports each result.

1. The TUI has stored `15063ec5587491ad` as the version it was checked against.
2. No citation in the TUI quotes an *Aggregate exceptions* item by number, or reads *Settings
   preconditions* from `PUT /auth/settings`.
3. Edits on an archived account's transactions keep working, and the TUI sends `account_id`
   only when it changes.
4. The TUI's contract tests pass against an engine serving `15063ec5587491ad`.

## What the engine declined

Nothing; the hand-off answers no ask.

## Tasks

Approved by the owner on 2026-10-18.

3. **Every contract citation points at a part the live contract holds, where it says.** Each
   `(contract: …)` citation in the repo's code and docs is checked against the practice
   engine's `/openapi.json`: a quoted section, rule or tag name exists in the place the citation
   names (the general description, the tag, or the operation). The citations the trim broke are
   pointed at the rules' new homes and names, among them *Staleness* under `Exchange Rates`,
   *There is no restore*, and *Reserved names on rename*. A new live contract test reads every
   citation in the repo and fails on one the live contract does not hold, so the next move is
   caught by the tester's run. Passes check 2 of the engine's.
4. **The fixture drift check passes on the Edit form's tests.** The test of the never-`null`
   rule in [test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py) holds the local
   names `note`, `operation` and `transaction`, which the drift script reads as fixture keys the
   engine does not serve. `python scripts/check_fixture_drift.py --engine-url
   http://127.0.0.1:8002` reports no fixture key the engine does not serve, by rewording the
   test or listing the names as local in the script, whichever the script's own rules call for.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `c4327854a6d6e301` (exclusive) to `15063ec5587491ad` (inclusive),
  answering every section of the hand-off named above.
- **Done when, checked:** the four checks in "The engine's checks" above, with the tester's
  results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
