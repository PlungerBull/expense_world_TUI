# Caught up with contract `fab230c456c2dba2`: an account becomes a person and back

2026-10-22

## Covers

Contract `56a43798fc1f2915` (exclusive) to `fab230c456c2dba2` (inclusive), the account half of
the hand-off "Every bank line carries an engine-given code and an optional statement-line
reference, an account can become a person and back, and a create sent again answers
`ID_EXISTS` before anything else" (shipped 2026-10-21). Its other half was answered in the reply
for contract `54fd1012f7d60abc`. The version to start the next catch-up file from is
`996986490b68f05e`, the newest this client holds (its reply is sent alongside this one).

What the TUI does with it:

- `t` on the Accounts screen sends `POST /accounts/{id}/make-person` on a bank account and
  `POST /accounts/{id}/make-account` on a person, at once and with no question. The list reads
  again with the cursor on the account in its new group, and Home shows it there.
- A refusal is shown in your words, top-level message and field message both. On
  `HAS_OPENING_BALANCE` the app adds one line saying to empty the opening balance first.
- The sheet import lists accounts with people and archived ones when it matches by name and
  currency, so a re-run after a conversion reuses the person instead of creating the name again.
- The live contract suite covers both routes: an account with transactions becomes a person and
  back keeping its id, name, currency, colour, balance and transactions, `version` up by one,
  listed and on the dashboard in its new group, `sort_order` at the end of that group;
  `KIND_UNCHANGED`, `HAS_OPENING_BALANCE` and `ACCOUNT_ARCHIVED` each write nothing; an unknown
  id is `NOT_FOUND`; a send under the same key is replayed and flips once.

## Done when, checked

Run against the practice engine on 2026-10-22, at contract `996986490b68f05e` (the whole live
contract suite passed, 139 tests).

1. **A real account becomes a person and back from the Accounts screen, and each refusal shows
   its reason:** worked. A bank account with two transactions and a balance of 110.00 became a
   person and then a bank account again: the same id, balance and transactions, `version` 1 → 2 →
   3, moving between `bank_accounts` and `people` on `/dashboard`. Each refusal showed its reason
   and changed nothing:
   - `HAS_OPENING_BALANCE`: "The account has an opening balance, which a person account cannot
     carry. Delete the opening-balance transaction first." / `account_id`: "Must be an account
     without an opening balance: a person cannot carry one."
   - `KIND_UNCHANGED`: "The account is already a person account." / `account_id`: "Must be a
     real account: this one is already a person."
   - `ACCOUNT_ARCHIVED`: "The account is archived. Unarchive it first."
2. **A sheet-import re-run after a conversion finds the converted account and creates no
   duplicate:** worked. A sheet with ALEJO in soles and dollars imported as three accounts; after
   ALEJO PEN became a person, the re-run printed `Accounts: created 0, reused 3` and
   `Transactions: created 0, already-present 4, failed 0`, leaving one ALEJO PEN.

## Contract problems found

- **What becomes of an account's reconciliations when it becomes a person is unstated.**
  `POST /accounts/{account_id}/make-person`, the "People / Person Accounts" tag and the
  "Reconciliations" tag say nothing about it. The practice engine (2026-10-22) accepts
  make-person on an account with a draft reconciliation and keeps the draft
  (`GET /reconciliations?account_id=` still lists it), and `POST /reconciliations` on a person
  answers `201`: the create asks only for an active, non-archived account. This client offers
  reconciliations only on real accounts. Please state whether a person may have reconciliations,
  and what happens to an account's existing ones when it becomes a person.
- **Minor:** each refusal's field message is in the contract word for word, but its top-level
  message is not (for example `HAS_OPENING_BALANCE`'s "Delete the opening-balance transaction
  first."). Nothing here depends on it.

## Asks this closes

None.
