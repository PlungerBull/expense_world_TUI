# An account and its opening balances save in one write

Raised 2026-10-31.

## Why

A client's account form takes the account (its name, colour, statement code and, on a new
account, its currencies) together with an opening balance for each currency. The person fills
it in once and saves once.

The engine takes that save as several writes, each atomic on its own:

- the account: `POST /accounts` on a new account, `PUT /accounts/{id}` on an edit;
- then, for each currency whose opening balance changed, one more write: a new opening balance
  is `POST /accounts/{id}/opening-balance`, a changed one `PUT /transactions/{id}`, a cleared one
  `DELETE /transactions/{id}`.

The writes go one after another, so the save as a whole is not atomic. Say the account and its
soles' opening balance land and the dollars' opening balance is refused (`FUTURE_DATE`,
`SEALED_PERIOD`, `ZERO_AMOUNT`, `LOCKED`, …). The person now has a half-saved account. Every
client then has to:

- track which writes landed;
- tell the person which half went through and which did not;
- send again only what is left, never what already saved;
- give a write that was cut off with no answer the same care.

The terminal app does all of this. The web and iPhone apps would each have to rebuild it, and a
slip in any one of them sends an opening balance twice or loses one without telling the person.

The separate opening-balance route should stay: seeding one currency on its own is still a
use. This ask adds a way to save the whole form in one request.

## The ask

Let one request save the account together with any of its currencies' opening balances, all or
nothing:

- **On create:** each entry of `POST /accounts`'s `currencies` may carry an optional opening
  balance, for example
  `{"currency_code": "USD", "opening_balance": {"transaction_id": "…uuid…", "amount_cents": -4550, "date": "2026-01-01T00:00:00-05:00"}}`,
  judged by the same rules as `POST /accounts/{id}/opening-balance`.
- **On edit:** `PUT /accounts/{id}` (or a route beside it) may set, change or clear the opening
  balance of any currency the account holds, alongside the name, colour and code, for example
  `"opening_balances": {"USD": {"amount_cents": -4550, "date": "…"}, "PEN": null}`.
- **Refusals:** each one is keyed to the currency it is about (for example
  `currencies.<i>.opening_balance.date`, or `opening_balances.USD.amount_cents`), so a client can
  point at the right field. A refusal of any part means nothing is written.

The exact shape is the engine's call. What matters is one request, all or nothing, with each
refusal naming its currency.

## Done when

- One request creates an account with its currencies and each one's opening balance, all or
  nothing.
- One request edits the account's name, colour and statement code and sets, changes or clears
  any currency's opening balance, all or nothing.
- Each refusal names the currency and field it is about, and the contract describes both
  requests, their refusal order and how they answer.

## What this client removes once it lands

The account form's chain of writes, one per opening balance; its record of which writes in a
save landed; the note telling the person which half of a save went through; and the logic that
sends again only the writes still left.
