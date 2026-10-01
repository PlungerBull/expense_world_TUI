# Catch up to engine contract 7e7cfb294fe255c7

**Status: approved** (owner, 2026-09-30); the loop runs on it. It
runs **before** the other draft specs (owner, 2026-09-30). When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The engine coders changed the engine. The app was last checked against contract
`5f65d4448df149d4`; the engine is now at `7e7cfb294fe255c7`. The app has to follow, so that it
works against the engine as it is now.

- **Moving a transaction that sits in an unfinished reconciliation to another account works
  again.** The engine now refuses that move unless the app also says what happens to the
  reconciliation (contract: "Assigning transactions") (contract: PUT /v1/transactions/{id}). The
  app takes the transaction out of its old reconciliation as part of the move (owner,
  2026-09-30), from the edit form and from `b` in Home alike, and a short note says so
  (owner, 2026-09-30): the edit form says `Saved. It left its reconciliation.`, and `b` in Home
  says `3 rows → BCP USD · 2 left their reconciliation`.
- **The other changes since `5f65d4448df149d4` need no work**, so the new version is simply
  recorded:
  - `93a62b40ae9751d8` is wording only.
  - `ee34e2bf828b9d4f` refuses a hashtag named twice in one request (`DUPLICATE_IN_REQUEST`).
    The app never sends one twice: quick-add drops the repeat and the hashtag pickers choose
    each tag once.
  - `7e7cfb294fe255c7` refuses an imported bank row whose `id` the ledger already has
    (`ID_EXISTS`). The bank import gives every row a fresh `id` on every run, so it never sends
    one the ledger has.

Nothing the owner sees changes apart from the move working and its note.

## How the owner knows it is done

1. The practice-engine check passes: the contract version matches and no fixture differs.
2. The live contract suite passes against the practice engine.
3. In `expense world`, a transaction in an unfinished reconciliation moves to another account,
   from its edit form and with `b` in Home, and the app says it left its reconciliation.
4. A locked-field or sealed-period edit in `expense world` still shows its hint.

## Tasks

Approved by the owner, 2026-09-30.

1. **A move takes the transaction out of its reconciliation.** The edit form and the bulk `b`
   in Home add `reconciliation_id: null` to a write that changes a transaction's `account_id`
   (contract: "Assigning transactions"), and show the note from "What it must do" when the
   moved transaction was in a reconciliation. Passes if:
   - no TUI path can send an `account_id` change without `reconciliation_id`;
   - a row whose account does not change sends no `reconciliation_id`, so `b` onto the account
     a selected row is already on never takes it out of its reconciliation;
   - a row in a completed reconciliation is still refused with the lock hint, as today;
   - unit tests cover each of these, and a contract test proves the move against the
     practice engine.

   The flat `expense transactions update --account-id` is not changed: the TUI-only spec
   ([tui-only-plan.md](tui-only-plan.md)) deletes it.
2. **Record contract version `7e7cfb294fe255c7`** (`--record-version` against `:8002`), in the
   commit that finishes task 1. Passes if the drift check exits 0.
