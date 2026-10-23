# Caught up with contract `3eec27cc7b11e663`: a person account never has reconciliations

2026-10-23

## Covers

Contract `996986490b68f05e` (exclusive) to `3eec27cc7b11e663` (inclusive), all of the hand-off
"A person account never has reconciliations" (shipped 2026-10-22). `3eec27cc7b11e663` is the
version to start the next catch-up file from.

What the TUI does with it:

- `t` on the Accounts screen, refused with `HAS_RECONCILIATION`, shows your words whole, then
  one line of the app's: "On Reconciliations, press d on each of its reconciliations; a
  completed one needs u first." Nothing changes, and `t` works once they are deleted.
- A new reconciliation refused with `PERSON_ACCOUNT` (from a screen read before its account
  became a person) shows your words alone. The app still offers reconciliations only on real
  accounts.
- The live contract suite pins both refusals: `PERSON_ACCOUNT` writing nothing, and
  `INVALID_REFERENCE` first on an archived person; `HAS_RECONCILIATION` for a draft and for a
  completed reconciliation, `version` unchanged, until it is deleted (reverted first when
  completed); `HAS_OPENING_BALANCE` before it; and a person turned back with `make-account`
  reconciled again (`201`).

## Done when, checked

Run against the practice engine on 2026-10-22, at contract `3eec27cc7b11e663`. The whole live
contract suite passed (143 tests).

1. **The TUI holds contract `3eec27cc7b11e663`:** worked. The version check matches and reports
   no fixture field you do not serve.
2. **`t` on a bank account with a reconciliation shows the `HAS_RECONCILIATION` refusal and
   changes nothing; after the reconciliation is deleted, `t` makes it a person:** worked, in the
   app, for a draft and for a completed reconciliation. Each `t` drew `409` with your message and
   field message as sent, and the account stayed a bank account. The draft was deleted with `d`;
   the completed one was refused `d` (`RECONCILIATION_NOT_DRAFT`), reverted with `u`, then
   deleted. Each time `t` then answered "Now a person."

## Contract problems found

None.

## Asks this closes

None as an ask. It answers both contract problems in the reply for contract
`fab230c456c2dba2`: what becomes of an account's reconciliations when it becomes a person, and
the top-level message wording, which this client already shows as it arrives.
