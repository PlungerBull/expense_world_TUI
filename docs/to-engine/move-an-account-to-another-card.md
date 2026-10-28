# Yes to moving an account to another card, with the limits you proposed; no to the sheet import refusing a name used in two currencies

Raised 2026-10-27, answering the engine coders' proposal of 2026-10-27.

## Why

Since contract `e06456a20aca6e4c` every real account sits on one card, and "An account never
changes card" (`PUT /accounts/{id}`). The card an account lands on is chosen once, at its create,
and a wrong choice cannot be undone: the only way out is turning the account into a person and
back, which an opening balance or any statement refuses.

The owner's first import shows why that matters. The sheet names an account by its name and
currency only, and alike-looking names mean different things: the Visa's soles and dollar
accounts are one card; each person holding both currencies must be alone on a card to become a
person; each savings account is a card of its own, since its paper holds one currency. A client
creating the sheet's accounts cannot tell these apart, so either the owner builds the Visa's card
by hand before the import, or every account gets a card of its own and the cards are put together
afterwards, which needs a move. Every client creating accounts for a person's existing bank
products meets the same choice.

## The ask

**Yes to the move action, exactly as you proposed:**

- One action, "move this account to that card". Pairing is moving the dollar account onto the
  soles account's card; unpairing is creating a new card, then moving the account onto it.
- The card the account leaves is deleted when the move leaves it empty, as `make-person` deletes
  it, with its own `DELETED` entry.
- Refused when the account has ever been in a statement, a deleted one included.
- The target card must be live, not archived, hold no account in that currency, and have no
  statement yet.
- It replaces the rule that an account never moves between cards; the account keeps its id, its
  transactions and its balance.

**The optional sheet-import check: this client's view is no, as a refusal. It is the owner's
choice.** You offered that `POST /transactions/import-sheet` refuses a name used in both
currencies (say `BCP Signature` PEN and USD) when its two accounts sit on different cards. A name
in two currencies does not always mean one card: each of the owner's four people in both
currencies (`ALEJO` PEN and USD, and the others) must be alone on a card to become a person, and
two different bank products may share a name. A refusal would bake that guess into the engine.
At most, the dry run could flag such names (a warning on `names`) for the person to check, and
never refuse.

## Done when

- The contract states the move route, its body and every refusal above, each with its reason and
  key, and the rule "an account never changes card" is replaced by it.
- Moving an account in no statement onto a live card holding no account in its currency, with no
  statement, answers the account on its new card; its old card, left empty, is deleted with its
  own `DELETED` entry; both cards' `account_ids` read the change.
- Each refusal answers as stated and writes nothing: an account once in a statement (a deleted
  one included), an archived or deleted target card, a target holding that currency, a target
  with a statement.
- If the owner wants the sheet-import flag: a dry run of a sheet using one name in both
  currencies, its two accounts on different cards, answers a warning naming it, and nothing is
  refused.

## What this client removes once it lands

Nothing: it adds putting a card's accounts together and apart in the app, and the first import
uses it to put the Visa's two accounts on one card.
