# Catch up with the contract's trimmed and corrected wording

**Status: draft, 2026-10-18.** Its tasks wait for the owner's approval.
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

Drafted 2026-10-18; wait for the owner's approval.

1. **The Edit form empties a note with `""`.** An emptied note sends `description: ""`, never
   `null`, which the engine refuses as `NOT_NULL` (contract: PUT /v1/transactions/{transaction_id}).
   Every other field the form sends is checked against the same rule: a field the form lets the
   owner empty sends what the contract accepts for it, or the form refuses the empty value
   before sending. Unit tests: an emptied note sends `""` and the form says `Saved.`; no field
   the form sends is ever `null` unless the contract lets that field clear with `null`. A live
   contract test: `PUT` with `description: ""` empties the note, and `description: null` is
   `422` `NOT_NULL`. Passes 1 above.
2. **The archived-account rule has a live contract test.** On a transaction whose account is
   archived, `PUT` of `category_id` and `description`, a split and a delete go through, and a
   `PUT` that sends the archived account's `account_id`, even unchanged, is `422`
   `INVALID_REFERENCE` on `account_id`. A unit test pins that the Edit form and the ledger's
   bulk `b` never put an archived account's id in a body: the form sends `account_id` only when
   it changes, and the account picker offers no archived account. Passes 2 above and check 3 of
   the engine's.
3. **Every contract citation points at a part the live contract holds, where it says.** Each
   `(contract: …)` citation in the repo's code and docs is checked against the practice
   engine's `/openapi.json`: a quoted section, rule or tag name exists in the place the citation
   names (the general description, the tag, or the operation). The citations the trim broke are
   pointed at the rules' new homes and names, among them *Staleness* under `Exchange Rates`,
   *There is no restore*, and *Reserved names on rename*. A new live contract test reads every
   citation in the repo and fails on one the live contract does not hold, so the next move is
   caught by the tester's run. Passes check 2 of the engine's.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `c4327854a6d6e301` (exclusive) to `15063ec5587491ad` (inclusive),
  answering every section of the hand-off named above.
- **Done when, checked:** the four checks in "The engine's checks" above, with the tester's
  results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
