# A person account never has reconciliations

**Status: approved (owner, 2026-10-22).** A catch-up spec: it folds
in the engine's hand-off "A person account never has reconciliations" (shipped 2026-10-22).

---

## Why

The last reply to the engine said the contract did not say what becomes of an account's
reconciliations when it becomes a person. The engine answers with the owner's ruling
(2026-10-22): a person never has reconciliations, the same way it never carries an opening
balance, since a reconciliation checks the ledger against a bank statement and a person sends
none. So `t` on a bank account with a reconciliation, a draft or a completed one, is now refused
until its reconciliations are deleted, and a reconciliation can no longer be started on a person.
The app already offers reconciliations only on bank accounts.

## What it must do

- The app holds the engine's new contract version, so the version check passes again.
- `t Make person` on an account with a reconciliation shows the engine's refusal and changes
  nothing; once its reconciliations are deleted, `t` makes it a person.
- A reconciliation started from a screen read before its account became a person shows the
  engine's refusal in its words.
- The refusal on `t` is drawn as a mockup and picked by the owner before it is built:
  [expense-world-person-reconciliations.html](../mockups/expense-world-person-reconciliations.html).

## How the owner knows it is done

1. A bank account with a draft reconciliation is refused by `t`, with the engine's reason and
   the app's line from pick A, and stays a bank account.
2. After that draft is deleted on Reconciliations, `t` makes it a person.
3. The same with a completed reconciliation: refused, then `u` and `d` on it, then `t` works.

## Catching up with the engine

**Catches up to contract `3eec27cc7b11e663`:** every contract change after `996986490b68f05e`
up to it. Two refusals are new, and nothing else moved:

- `POST /reconciliations` on a person: `422 VALIDATION_ERROR`, reason `PERSON_ACCOUNT` on
  `account_id`, nothing written. An archived account, person or not, still answers
  `INVALID_REFERENCE` first.
- `POST /accounts/{id}/make-person` on an account with a live reconciliation, draft or
  completed: `409 CONFLICT`, reason `HAS_RECONCILIATION` on `account_id`, nothing written. It
  comes after `ACCOUNT_ARCHIVED`, `KIND_UNCHANGED` and `HAS_OPENING_BALANCE`. A deleted
  reconciliation does not count.

`make-account` is unchanged: a person turned back into a bank account can be reconciled again.

**The engine's checks** — its "Done when". The tester's acceptance check runs them, and the
reply reports each result.

1. The TUI holds contract `3eec27cc7b11e663`.
2. `t` on a bank account with a reconciliation shows the `HAS_RECONCILIATION` refusal and
   changes nothing; after the reconciliation is deleted, `t` makes it a person.

**What the engine declined:** putting a refusal's top-level message in the contract word for
word. The contract's "Base Conventions" already says clients switch on `code` and `reasons`,
never on wording, and the texts may be reworded; the app shows the engine's words as they arrive,
which the engine confirms is right. Nothing to do here.

**Questions for the owner:** none open.

## Tasks

Approved by the owner 2026-10-22, who picks A in
[expense-world-person-reconciliations.html](../mockups/expense-world-person-reconciliations.html):
the engine's words, then `On Reconciliations, press d on each of its reconciliations; a completed
one needs u first.`

2. **The live contract suite knows both refusals.** `POST /reconciliations` on a person is `422`
   `PERSON_ACCOUNT` on `account_id`, nothing written; on an archived person it is still
   `INVALID_REFERENCE`. `make-person` on an account with a draft reconciliation, and on one with
   a completed reconciliation, is `409` `HAS_RECONCILIATION` on `account_id`, `version`
   unchanged; after the draft is deleted, or the completed one reverted and deleted, it is `200`.
   An account with both an opening balance and a reconciliation answers `HAS_OPENING_BALANCE`. A
   person turned back with `make-account` can start a reconciliation again (`201`). Each test
   cites the contract part stating its rule. Passes if the tests pass against `:8002`.
3. **`t` and a new reconciliation show the new refusals.** `t Make person` refused with
   `HAS_RECONCILIATION` shows the engine's words whole, with the app's line from pick A, and
   the list stays as it was; a new reconciliation refused with `PERSON_ACCOUNT` shows the engine's
   words, with no line of the app's. [tui.md](../tui.md) "When the engine says no" gives both
   their rows, and its `t` paragraph names the new refusal. Unit tests: each refusal, and `t`
   working once the fake engine no longer refuses. Passes the owner's checks 1 to 3 and the
   engine's check 2.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `996986490b68f05e` (exclusive) to `3eec27cc7b11e663` (inclusive), the
  hand-off named above. `3eec27cc7b11e663` is the version to start the next catch-up file from.
- **Done when, checked:** the two engine's checks above, with the tester's results.
- **Contract problems found:** what the build and the tester's run find; "none" when none.
- **Asks this closes:** none as an ask file; it answers the two contract problems in the reply
  for contract `fab230c456c2dba2`.
