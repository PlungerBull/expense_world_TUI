# Create a bank account and its own card in one write

Raised 2026-10-27.

## Why

Contract `e06456a20aca6e4c` puts every real account on a card, and `POST /accounts` requires
`card_id`: "**Required:** `id`, `name`, `currency_code`, `card_id`". A card is created apart,
first: `POST /cards` "Creates a card, holding no account", and *Cards* says "Create the card first
with `POST /cards`, then its accounts on it with `POST /accounts`". `POST /accounts/{id}/make-account`
reads the same: "To give it a card of its own, create the card first with `POST /cards`."

Most accounts are the only account on their card (a savings account, a cash wallet, a loan), so
most creates are two writes, and they are not one unit:

- **A refused account leaves an empty card.** `POST /accounts` is judged after the card exists:
  a name taken in that currency (`NAME_EXISTS`), the account cap (`LIMIT_REACHED`), an unsupported
  currency. The card stays, holding no account, until the client deletes it with a third write,
  which can fail too (the network, a closed app).
- **Two round trips per account**, and a bulk create, such as the terminal app creating every
  account a spreadsheet names before importing it, doubles its writes.
- **Each client rebuilds the same pair of writes** and its cleanup, each in its own way.

## The ask

Let `POST /accounts` and `POST /accounts/{id}/make-account` create the account's card in the same
write: in place of `card_id`, a `card` object, `{"id", "name", "statement_code"}`, judged as
`POST /cards` judges it. Both are written, or neither is. Sending both `card_id` and `card`, or
neither, is a `422`. A refusal of the card is keyed under `card.` (`card.name` `NAME_EXISTS`,
`card.statement_code` `STATEMENT_CODE_EXISTS`); the response is the account, its `card_id` the new
card's. Activity writes the card's `CREATED` entry and the account's, and idempotency covers both.

## Done when

- One `POST /accounts` with `card` answers `201`, the account on a new card holding only it.
- A refused account, for any reason, leaves no card behind, and a refused card leaves no account.
- `make-account` with `card` turns a person into a real account on a new card in one write.
- The same request sent again under the same key answers the stored response and writes nothing.

## What this client removes once it lands

The terminal app stops creating a card before each new account and deleting the card when the
account is refused; its New account form, its person-to-account key and its spreadsheet import's
step that creates missing accounts each send one write per account instead of two.
