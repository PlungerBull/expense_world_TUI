# The live tests for moving an account, and making and unmaking a holder

Catches up to contract `e020782e3579d011`, from `e7393dd869963db1`: the engine's hand-off of
2026-10-28, "An account moves between holders, a holder is made and unmade with its accounts, and
a holder's bank lines list in one read" (`3e472b3256dcdc69` to `256f3190cf24fc36`; this client
recorded it as `f00534abdde7fa82`, a draft that never shipped), and the parts on holders of its
hand-off of 2026-10-28, "A person is a holder; unpairing is one write; the PDF upload moves a line
one day off; the change log reaches back; your practice engine serves only shipped code"
(`4dd95f836dba7be2` to `e020782e3579d011`): a holder's kind, a person's move, a person taking no
statement and unpairing in one write. The screens it asks for are in
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) (the move, a holder
made with its accounts, a delete refused while a statement holds the account) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md)
(a holder's lines in one read, a flagged line's two paths); this spec is their live tests.

**Status: approved by the owner on 2026-10-28, with its tasks; its points and tasks, changed for
the hand-off "A person is a holder; …", wait on the owner's approval again.** It runs after
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
whose shared helpers its tests use, and waits on nothing else. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine shipped five new things on 2026-10-28 (contract: "Holders"):

- an account in no statement moves to another holder, which is how a card's two currencies are
  paired and unpaired (contract: POST /v1/accounts/{account_id}/move);
- deleting a holder's last account deletes the holder too (contract: DELETE /v1/accounts/{account_id});
- a holder is created with its accounts in one write (contract: POST /v1/holders);
- a holder's bank lines are listed and counted in one read, both currencies together
  (contract: GET /v1/bank-lines);
- an account a live statement holds is not deleted (contract: DELETE /v1/accounts/{account_id}).

and, in its later hand-off:

- a holder has a kind, bank or person (`is_person`), and `GET /holders` lists bank holders
  first (contract: "Holders", "Its kind");
- a person moves between person holders, and a move onto the other kind is refused
  (contract: POST /v1/accounts/{account_id}/move);
- the move makes the holder it moves onto, in one write, all or nothing
  (contract: POST /v1/accounts/{account_id}/move);
- a person holder takes no statement (contract: POST /v1/statements).

Each new engine capability gets its live test in this client, so a wrong rule shows here first.
Nothing you see changes.

## What it must do

1. **The move is tested live:** pairing an account onto another holder and unpairing it onto a
   new one in one write, its old holder deleted when left empty, a person between person
   holders, and each refusal, first one first, writing nothing; a refused unpairing leaves
   `GET /holders` as it was (contract: POST /v1/accounts/{account_id}/move).
2. **A holder's life is tested live:** created with its accounts in one write, all or nothing,
   a refused item named by its place; a person holder with its people, listed after the bank
   holders; deleted with its last account, a delete of it afterwards
   answering `404` (contract: POST /v1/holders) (contract: DELETE /v1/accounts/{account_id}).
3. **A holder's bank lines are tested live:** listed and counted by holder, both currencies
   together, paged; with an account of another holder, nothing (contract: GET /v1/bank-lines).
4. **An account a live statement holds is not deleted,** and is once the statement is
   (contract: DELETE /v1/accounts/{account_id}); **a person holder takes no statement**
   (`PERSON_TAKES_NO_STATEMENT`, contract: POST /v1/statements).

## How the owner knows it is done

1. The live suite passes against the practice engine, these tests included.
2. A test run leaves nothing on the practice user.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-28; they wait on the owner's approval. Each needs the practice engine, which the
orchestrator starts before the task and stops after it. Each builds its records through 2a's
`Scratch` and cites the live contract.

1. **The move (builder).** A new tests/contract/test_account_move.py: pair, then unpair; the old
   holder `404` when left empty; unpairing with `holder` in one write, of the account's kind;
   a person paired and unpaired between person holders; `ACCOUNT_ARCHIVED`,
   `STATEMENT_KEEPS_ACCOUNT` (a deleted statement included), `HOLDER_UNCHANGED`,
   `INVALID_REFERENCE`, `HOLDER_KIND_MISMATCH`, `HOLDER_CURRENCY_TAKEN` and
   `HOLDER_HAS_STATEMENT`; `holder` refused on `holder.<field>` (`EMPTY`, `ID_EXISTS`,
   `NAME_EXISTS`, `STATEMENT_CODE_EXISTS`, `UNKNOWN_FIELD` for `is_person` and `accounts`);
   neither or both of `holder_id` and `holder` refused (`REQUIRED`, `CONFLICTING_PARAMETERS`);
   each writing nothing.
   *Passes if:* the file passes live, every refusal reads back unchanged, and a refused unpairing
   leaves the whole `GET /holders` body as it was.
2. **A holder made and unmade (builder).** In the holder tests: `POST /holders` with two
   accounts answering both in `account_ids`; a person holder with two people
   (`is_person: true`), listed after every bank holder; `is_person` refused on `PUT /holders/{id}`;
   a refused item (`accounts.<i>.name` `NAME_EXISTS`, two in one currency) leaving no holder; deleting the last account leaving `GET /holders/{id}`
   and `DELETE /holders/{id}` at `404`; a holder of two keeping the other.
   *Passes if:* those tests pass live and leave nothing.
3. **Lines by holder, and a delete a statement stops (builder).** `GET /bank-lines` and
   `/bank-lines/count` with `holder_id`, both currencies together, paged, with an account of
   another holder listing nothing; `IN_LIVE_STATEMENT` on an account a draft holds, and `200`
   once the statement is deleted; `PERSON_TAKES_NO_STATEMENT` on `POST /statements` naming a
   person holder.
   *Passes if:* those tests pass live and leave nothing.

## Reply to the engine

Written into [to-engine/](../to-engine/) when this spec is done, with the tester's results.

- **Range:** `3e472b3256dcdc69` → `256f3190cf24fc36`, then `4dd95f836dba7be2` →
  `e020782e3579d011` (its parts on holders), shared with
  [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) and
  [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).
- **The engine's "Done when" checks this spec reports on:** none of its own; it reports the move,
  the delete with the last account, a holder made with its accounts, the lines by holder and
  `IN_LIVE_STATEMENT` as the live suite proves them.
- **The asks it closes:** none; the cards and statement screen specs close them.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
