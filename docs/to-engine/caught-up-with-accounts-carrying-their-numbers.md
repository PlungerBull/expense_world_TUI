# Caught up with contract 1002f105c6bacdf1: an account's bank, its numbers over time and its built name, the one-write account form and the PDF checked against its account

2026-11-09

## Covers

Part 2 of the reply to the hand-off of 2026-11-08, contract `385b112ad7f34bb8` to
`1002f105c6bacdf1`: sections 6, 12 and 13. Part 1 covered the rest. Checked against the practice
engine serving `9b3b43429d8bd11e`; the client's live contract suite ran green there (374 passed,
19 expected failures, which wait on the loose-lines and sheet-import asks).

## Done when, checked

- **A bank account is made from its bank and an optional last 4, and the engine names it:**
  worked. A bank account made with `BCP` and `9471` reads `BCP-9471` on every screen; one made
  with no number reads `BCP`; a person keeps its typed name. The client sends no `name` for a bank
  account and builds none.
- **A replacement card keeps the account:** worked. `new_number` from 2026-05-01 ended the old
  number on 2026-04-30, the name followed the new card, and the account kept its id, balance and
  completed statement. A start day inside a completed month was refused
  `NUMBER_IN_COMPLETED_STATEMENT`, naming the statement, with nothing written.
- **A number fixed, moved or removed:** worked. A removal made the number before it current again,
  and removing the last one named the account `BCP`. `FIRST_NUMBER_HAS_NO_START` and
  `NUMBER_START_NOT_LATER` were refused on their keys, with nothing written.
- **A kind change takes what the engine needs:** worked. `make-person` takes the name typed;
  `make-account` takes the bank and an optional last 4 and builds the name; a `name` sent to
  `make-account` is `NAME_BUILT`.
- **The account form saves in one write:** worked, on create and edit. An account with two
  currencies and their opening balances was one `POST /accounts`. One `PUT /accounts/{id}` set,
  changed or cleared opening balances with the account's own fields. A refused entry left nothing
  written, and the client showed the refusal on the line its key names
  (`currencies.1.opening_balance.date`, `opening_balances.USD.date`).
- **A PDF sent to the wrong account is refused:** worked, on the dry run and the apply, naming
  both numbers, with nothing written. An account with no number was refused
  `ACCOUNT_HAS_NO_NUMBER` (after `NO_STATEMENT_CODE`). The right account's paper closed its month,
  and a replaced card's earlier month closed with the old number's paper.
- **Section 6, the sheet import's `ambiguous` names:** taken up with the client's official
  import, which rewrites the step that creates names; not yet built.

## Contract problems found

- None. One observation: `opening_balances` takes up to 10 entries, but `GET /currencies` lists
  two, so a set, a change and a clear of three currencies in one request cannot be built on the
  practice engine; the client proved them across two requests.

## Asks this closes

- An account and its opening balances save in one write
- Save an account's changes and its opening balances in one write, whole or not at all
- An account carries its bank and its card numbers over time, and a PDF is checked against them
