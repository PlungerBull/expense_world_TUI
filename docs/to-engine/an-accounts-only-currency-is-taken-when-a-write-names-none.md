# An account's only currency is taken when a write names none

Raised 2026-10-31.

## Why

Since `f82426fb0a099676` a transaction names its account and its currency as two fields. Most
accounts hold one currency, so for most writes the currency is not a choice: the account holds
nothing else. The owner's rule for every client is that an account holding one currency asks
for none, and only an account holding several makes the person pick.

The engine does not follow that rule today:

- `POST /transactions` (and each batch item) requires `currency_code`, even on an account holding
  one currency.
- `PUT /transactions/{id}` and `PUT /bank-lines/{id}` sent `account_id` alone move the line "to
  the same currency on that account", and refuse it (`CURRENCY_NOT_HELD` on `account_id`) when
  that account holds one currency and it is another. Moving a dollar row to a soles-only account
  needs `currency_code` sent too.

So every client reads the account's currencies before each write, decides "one currency, so use
it", and fills `currency_code` in itself: the terminal app does it in its quick-add line, its
edit form and its move of selected rows to another account. The web and iPhone apps would each
repeat it, and a client that forgets refuses writes the person never had a choice about.

## The ask

When a write names an account and no currency, and the account holds exactly one live currency,
the engine takes that currency:

- **`POST /transactions` and each batch item:** `currency_code` is optional. Omitted, it is the
  account's only currency. On an account holding several, omitted is `422` on `currency_code`
  (`REQUIRED`), its message naming the account's currencies, so a client can show what to pick
  from.
- **`PUT /transactions/{id}` and `PUT /bank-lines/{id}` sent `account_id` alone:** the line keeps
  its currency when the new account holds it, as today. When the new account holds one currency
  and it is another, the line takes that currency, its amount as it is (no conversion: `-100.00`
  in dollars becomes `-100.00` in soles). When the new account holds several and not the line's,
  it stays `CURRENCY_NOT_HELD` on `account_id`.
- The answer names the currency taken (`currency_code` in the response, as today), and the
  activity entry records it like any other move.

## Done when

- A transaction created on a one-currency account with no `currency_code` lands in that
  currency, on a single create and in a batch; on a two-currency account it is `REQUIRED`, the
  message naming the currencies.
- A line moved by `account_id` alone onto a one-currency account in another currency lands in
  that currency, the amount unchanged.
- The contract states both rules, and the refusal order says where the `REQUIRED` falls.

## What this client removes once it lands

Reading the account's currencies to fill `currency_code` on a write: the quick-add line, the
edit form's account change and the move of selected rows to another account send `account_id`
alone and leave the currency to the engine. The client still reads the currencies to show them.
