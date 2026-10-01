# Catch up to engine contract 93a62b40ae9751d8

**Status: draft.** The owner reviews and completes this spec before the loop starts on it. It
runs **before** the other draft specs (owner, 2026-09-30). When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The engine coders changed the engine (reported 2026-09-29). The app has to follow, so that it
works against the engine as it is now.

- **Moving a transaction that sits in an open reconciliation to another account works again.**
  The engine now refuses that move unless the app also says what happens to the reconciliation:
  either take the transaction out of it, or put it in an open reconciliation on the new account
  (contract: "Assigning transactions") (contract: PUT /v1/transactions/{id}). When the app
  cannot do it, the message says which reconciliation the transaction is in and what to do.
- **Error hints show again.** The engine reworded its error messages and now tags each error
  with a fixed code (contract: "Error format") (contract: "Error reasons"). The app reads the
  code, never the wording, so a later rewording breaks nothing.
- **One test-engine guard goes.** The engine itself now refuses to start the test engine on
  mismatched databases, so the repo's own copy of that check is removed; the rule that the test
  engine runs on `:8002` stays.

Nothing the owner sees changes apart from the move working and the hints showing.

## How the owner knows it is done

1. The practice-engine check passes: the contract version matches and no fixture differs.
2. The live contract suite passes against the practice engine.
3. In `expense world`, a transaction in an open reconciliation moves to another account, and the
   app says what happened to its reconciliation.
4. A locked-field or sealed-period edit in `expense world` shows its hint, as before.

## Open questions for the owner

### What happens to its reconciliation when you move a transaction to another account?
Asked 2026-09-30 · Blocks: task 2
In `expense world` you move a transaction to another account from its edit form, or many at
once with `b` in Home. If a transaction sits in an open reconciliation, the engine needs to be
told what to do with it.
- **A.** Take it out of the reconciliation, silently; the app says so after the move. Nothing
  new to draw.
- **B.** Ask each time: take it out, or put it in an open reconciliation on the new account.
  A new screen — mockup first.

**Recommended:** A, because the old reconciliation is on the old account and cannot hold it any
more, and when you are reconciling the new account you assign it there anyway.

## Tasks

Draft, for the owner's approval.

1. **Record the new contract version** (`--record-version` against `:8002`), and update the unit
   fixtures the drift check flags.
2. **Moving an assigned transaction names its reconciliation.** Every path that changes a
   transaction's `account_id` also sends `reconciliation_id`: `null` to unassign, or a draft
   reconciliation on the new account. The engine's `ASSIGNED_TO_RECONCILIATION` reason gets a
   hint. Passes when no path can send an account change on an assigned transaction without
   `reconciliation_id`. Waits on the open question above.
3. **Match on error reasons, not wording.** Switch on `reasons` in `reconcile_cmd.py`
   `_period_hint` (`RANGE_INVERTED`, `PERIOD_OVERLAPS`), `_complete_hint`
   (`NO_TRANSACTIONS_ASSIGNED`, `UNASSIGNED_IN_PERIOD`), `_is_field_locked_422` (`LOCKED`), and
   the lock/sealed hint in `transactions_cmd.py` (`LOCKED`, `SEALED_PERIOD`,
   `RECONCILIATION_COMPLETED`); then delete `error_haystack`. Also: the sealed-period top-level
   message is no longer fixed; `POST /v1/transactions/batch` reports an unknown hashtag under
   `transactions.<i>.hashtag_ids`; `GET /v1/reports/monthly` field texts are full sentences;
   date/datetime format errors no longer start with "Value error, ". Passes when the code reads
   error wording nowhere.
4. **Drop the duplicate test-engine guard.** Remove the repo's check that a test-engine start
   command sets both `SUPABASE_DB_URL` and `ADMIN_DB_URL`; keep only the `:8002` rule.
