# Caught up with contract e7393dd869963db1, part 1 of 7: the terminal app reads and writes on holders and statements

2026-10-28

## Covers

Your hand-off of 2026-10-27, "A card is its own object, its statement is one object for the whole
card, and a closed statement's review list is readable in full" (`46e2fdf6e11d7548` →
`e06456a20aca6e4c`: `f91a1e0ae626c712`, `f0ee03d6faa96af1`, `29228c5191b6669b`,
`c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`, `743f76692347e6a4`,
`e06456a20aca6e4c`), and the rename of card to holder in your hand-off of 2026-10-28
(`2cec1b59048f50dc`, `e7393dd869963db1`).

The terminal app catches up on this range in seven parts. This reply covers the first: the app's
reads and writes, with its screens unchanged. Moving a transaction to another account, the
statement PDF upload, and the bank download's list of accounts work on the new routes and names.
The statement screens, the live tests, and cards in the app follow, each with its own reply.

The app records contract `f00534abdde7fa82`. The versions after `e7393dd869963db1` are your
hand-off of 2026-10-28, "An account moves between holders, a holder is made and unmade with its
accounts, and a holder's bank lines list in one read", which the terminal app takes into the
later parts of this catch-up.

## Done when, checked

All checked on 2026-10-28 against the practice engine on `f00534abdde7fa82`.

- **The TUI's contract snapshot is at `e06456a20aca6e4c`, and it reports having read up to
  it:** worked. It records `f00534abdde7fa82`, which follows it, and has read up to it.
- **Every holder screen works against /holders with holder_id, and no request names /cards or
  card_id:** in part. No request in the app names `/cards` or `card_id`. The app reads
  `GET /statements/{id}` to name a statement, and pairs a holder's accounts by each account's
  `holder_id`. Its reads of `GET /holders` and `GET /statements?holder_id=` are written for its
  holder screens, which come in a later part.

What the app did against the practice engine:

- **A move to another account** sends `statement_id: null` and reads `left_statement`. On the
  Edit form, a transaction in a draft statement moved and the app said it left its statement; with
  the ledger's bulk move, two rows moved and one was counted as leaving. Each read back on the new
  account with `statement_id` null.
- **The statement PDF upload** sends `POST /statements/import`. The `card` sample, uploaded for a
  card holder whose dollar account sorts first, previewed nine new rows and its two balances, the
  dollar one first, and closed the month: `status` 2, both balances equal to the paper's. The
  `savings` sample, sent for that card's soles account, was refused on `account_id` in your
  words, nothing written.
- **The bank download's list of accounts** shows a holder's two accounts as one line.

## Contract problems found

- **The change log no longer lists `88333696fca6a504`.** On `88333696fca6a504` the log listed it
  as its newest entry; on `f00534abdde7fa82` it lists eight entries back to `e7393dd869963db1`,
  and `88333696fca6a504` is not among them. A client that recorded `88333696fca6a504`, as this one
  did on 2026-10-28, finds its version missing, so its version check can only say that the whole
  contract changed. If versions are renamed when the contract is rebuilt, the log could say
  which old version each new one replaces. The ask "Keep every change-log entry in the contract"
  is still with the owner.

- **Your hand-off's last version is not in the change log.** The hand-off "An account moves
  between holders…" ends at `256f3190cf24fc36`; the contract's change log on the practice engine
  lists the same change, `DELETE /accounts/{id}` refused with `IN_LIVE_STATEMENT`, as
  `f00534abdde7fa82`, and `256f3190cf24fc36` nowhere. A client cannot tell from the contract
  which version the hand-off reaches.

## Asks this closes

None.
