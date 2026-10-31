# Removing a currency names the currency in every refusal

Raised 2026-10-31.

## Why

`DELETE /accounts/{id}/currencies/{code}` removes one currency from an account. Two of its
refusals are about that currency, yet they read as if they were about the whole account:

- `HAS_TRANSACTIONS`: a transaction is booked in the currency. It is keyed on `account_id`, with
  `"Must not be used by any active transaction."`
- `IN_LIVE_STATEMENT`: a live statement holds a balance for the currency. It is keyed on
  `account_id`, with `"Must be an account no live statement holds, draft or completed: delete the statement first."`

These are exactly the key and words `DELETE /accounts/{id}` uses when it refuses to delete the
whole account. `LAST_CURRENCY`, on the same route, is already keyed on `currency_code`.

So a client cannot tell from the refusal alone whether it is about the account or about one
currency, and the words never say which currency is meant. Each client has to remember which
route it called and change how it shows the same refusal to match. For example, "archive the
account instead" is good advice when a delete is refused, but the wrong advice when only a
currency's removal is refused, since archiving puts away every currency. Every client
would carry this special case, and one that forgets it shows the wrong guidance.

## The ask

On `DELETE /accounts/{id}/currencies/{code}`:

- key `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` on `currency_code`, as `LAST_CURRENCY` already
  is;
- name the currency in their messages, for example
  `"Must not be used by any active transaction in USD."` and
  `"Must be a currency no live statement holds, draft or completed: delete the statement first."`
  with the code in it.

`ACCOUNT_ARCHIVED` stays on `account_id`: it is about the account. `DELETE /accounts/{id}` keeps
its refusals as they are.

## Done when

- The currency removal's `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` are keyed on `currency_code`
  and their messages name the currency.
- The contract's refusal list for the route says so.

## What this client removes once it lands

The special case that shows a transaction-held refusal differently depending on whether it met
an account's delete or a currency's removal. A refusal's key alone then says what it is about.
