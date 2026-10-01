# Catch up to engine contract 84321bd839912a09

**Status: approved** (owner, 2026-09-30); the loop runs on it. It
runs **before** the other draft specs (owner, 2026-09-30). When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The engine coders changed the engine. The app was last checked against contract
`5f65d4448df149d4`; the engine is now at `84321bd839912a09`. The app has to follow, so that it
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
  - wording only: the *Assigning transactions* rule, and the `409` when a personal access key's
    id is taken. The app never creates personal access keys.
  - a hashtag named twice in one request is refused (`DUPLICATE_IN_REQUEST`). The app never
    sends one twice: quick-add drops the repeat and the hashtag pickers choose each tag once.
  - an imported bank row whose `id` the ledger already has is refused (`ID_EXISTS`). The bank
    import gives every row a fresh `id` on every run.
  - an opening balance on an unknown or deleted account answers `404`, not `422`. The app has
    no special message for either; it shows the engine's error.
  - renaming one system category to the other's default name is refused (`RESERVED_NAME`).
    The app shows the engine's error.

Nothing the owner sees changes apart from the move working and its note.

## How the owner knows it is done

1. The practice-engine check passes: the contract version matches and no fixture differs.
2. The live contract suite passes against the practice engine.
3. In `expense world`, a transaction in an unfinished reconciliation moves to another account,
   from its edit form and with `b` in Home, and the app says it left its reconciliation.
4. A locked-field or sealed-period edit in `expense world` still shows its hint.

## Tasks

Approved by the owner, 2026-09-30.

1. **Record contract version `84321bd839912a09`** (`--record-version` against `:8002`), and the
   tester runs `test_moving_an_assigned_row_needs_the_unassign_in_the_same_body`
   ([tests/contract/test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py))
   against the practice engine. Passes if the drift check exits 0 and that test passes.
