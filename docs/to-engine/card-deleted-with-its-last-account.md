# Delete a card with its last account, so no client leaves an empty card behind

Raised 2026-10-27.

## Why

On contract `e06456a20aca6e4c`, `DELETE /accounts/{id}` deletes the account and says nothing of
its card, so deleting a card's only account leaves the card live with `account_ids` `[]`. The card
keeps its name and its statement code: a card's name is unique "among the user's live cards", and
a statement code is held by one live card ("One card per code"), so the empty card blocks a new card
of that name or code until it is deleted with `DELETE /cards/{id}`, a second write.

The engine already deletes a card with its last account in one case: `POST /accounts/{id}/make-person`
says "**Its card is deleted with it.** A person is on no card: `card_id` becomes `null`, and the card
is deleted in the same write (`deleted_at` set, its own `DELETED` entry under
`resource_type = "card"`), releasing its name and its statement code."

An account can be deleted only while it holds no transaction (`HAS_TRANSACTIONS`), so the case is an
account created by mistake, often on a card made for it a moment before: the card is as much a
mistake as the account. Every client otherwise either leaves empty cards in its lists or sends the
second delete itself, with the failures a second write brings.

## The ask

When `DELETE /accounts/{id}` deletes the last live account of its card, delete the card in the same
write, as `make-person` does: its own `DELETED` entry under `resource_type = "card"`, releasing its
name and its statement code. A card that still holds another live account is untouched. State it
under *Cards* and on `DELETE /accounts/{id}`.

If a card left empty must be able to stay (to put a new account on it), say so instead, and say how
a client tells an empty card it should delete from one it should keep.

## Done when

- Deleting a card's only account leaves no live card: `GET /cards` no longer lists it, and its name
  and statement code are free.
- Deleting one account of a card holding two leaves the card with the other.
- The activity log holds the account's `DELETED` entry and the card's.

## What this client removes once it lands

The terminal app deletes no card after deleting an account, and shows no empty card left behind by
a delete.
