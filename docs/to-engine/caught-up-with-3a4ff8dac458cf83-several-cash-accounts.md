# Caught up with contract 3a4ff8dac458cf83: several cash accounts on the client's screens

2026-11-11

## Covers

Part 2 of the reply to the hand-off of 2026-11-11 ("A loose-lines refusal names its lines by id
in `error.details`…"), contract `ebadad5b9499610c` to `3a4ff8dac458cf83`: items 7 and 15, the
screens for a user holding several cash accounts. Part 1, the rest of the catch-up but the
loose-lines screen, is its own reply; part 3, the screen listing a refusal's loose lines, follows.
Checked against the practice engine serving `3a4ff8dac458cf83`: the client's whole live contract
suite ran green, 414 passed, plus 2 expected failures waiting on the sheet import's built names.

## Done when, checked

- **Three cash creates show `CASH-<n>` in rising order:** worked. Three cash accounts made from
  the client's New account form, which sends no name for cash, came back `CASH-0363`,
  `CASH-0364` and `CASH-0365` (earlier test runs had used the lower numbers, none reused), each
  shown under that name on the account list and the home screen.
- **An empty cash account deletes:** worked. The empty `CASH-0365` was deleted after the
  client's usual question and is gone from `GET /accounts`; `CASH-0364`, holding one
  transaction, was refused `HAS_TRANSACTIONS` on `account_id`, shown in the engine's words, and
  stayed as it was.
- **A line logged to a cash account by its name:** worked. A one-line entry naming `CASH-0364`
  landed on that account.
- **A person named `Efectivo`:** made, now that no cash account holds the name.

## Contract problems found

None.

## Asks this closes

None beyond those part 1 names.
