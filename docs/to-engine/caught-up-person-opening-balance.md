# Caught up with contract 4ac20e42cf8566ee: a person account carries an opening balance like any account

2026-10-28

## Covers

`e06456a20aca6e4c` → `4ac20e42cf8566ee` (`d34fc8d06ff652c4`, `4ac20e42cf8566ee`): part 1 of your
hand-off of 2026-10-28, "A person carries an opening balance, and a card is now called a holder
everywhere". Its part 2, the rename of card to holder (`2cec1b59048f50dc`, `e7393dd869963db1`), is
answered by the terminal app's cards and statements catch-up, with its own reply when that is
done.

The terminal app records contract `f00534abdde7fa82`, which follows these. The versions after
`e7393dd869963db1` are your hand-off of 2026-10-28, "An account moves between holders, a holder is
made and unmade with its accounts, and a holder's bank lines list in one read".

## Done when, checked

All checked on 2026-10-28 against the practice engine.

- **The TUI has recorded contract `e7393dd869963db1`:** worked. It records `f00534abdde7fa82`,
  which follows it.
- **A person's opening balance can be added from the app:** worked. A person's Edit form shows
  `opening` and `as of`, as a bank account's does. Adding `-150.00` dated 2025-12-31 to a person
  made by `POST /people` saved it: the person's balance read `-15000`, and its
  `opening_balance_transaction_id` named a transaction under `@Opening` on that person. The live
  suite also proves `201` under `@Opening`, and a second one refused `409 OPENING_BALANCE_EXISTS`
  with reasons exactly `{"account_id": "OPENING_BALANCE_EXISTS"}`.
- **make-person on an account with an opening balance succeeds:** worked. A bank account on its
  own holder, with an opening balance of `2,500.00`, became a person with one key, with no
  question. Its balance stayed `250000` and `opening_balance_transaction_id` was unchanged, its
  transaction still live. The holder answered `404` afterwards, as "Its holder is deleted with it"
  says.

The terminal app no longer has a line for `HAS_OPENING_BALANCE`, or for `PERSON_ACCOUNT` on the
opening-balance route.

## Contract problems found

- **The change log keeps only its five newest entries.** `x-changelog` in `/openapi.json` on
  `88333696fca6a504` lists `88333696fca6a504`, `7ec7a4bcf9e5a3fd`, `b2c5af41336bae5f`,
  `3e472b3256dcdc69` and `e7393dd869963db1`, and nothing older. A client whose last caught-up
  version is older, `e06456a20aca6e4c` here, can no longer read what changed since it, so its
  version check can only say that the whole contract changed. The ask "Keep every change-log
  entry in the contract" goes with this reply.

## Asks this closes

None. The opening balance on a person answers the owner's ruling of 2026-10-27, not an ask.
