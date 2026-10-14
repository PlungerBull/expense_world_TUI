# Say on each account which transaction is its opening balance

Raised 2026-10-14.

## Why

An account has at most one active opening balance, created by
`POST /v1/accounts/{account_id}/opening-balance` and edited or deleted afterwards through the
transactions API (contract: POST /v1/accounts/{account_id}/opening-balance). The account record
does not say whether it has one, or which row it is (contract: "Bank Accounts", "Account
response").

A client that shows an account's opening balance so the user can change or remove it has to find
the row itself: read `GET /v1/categories`, pick the category whose `system_key` is
`opening_balance`, then read `GET /v1/transactions` filtered by the account and that category. Two
extra calls every time the account is opened for editing, a lookup the contract never describes,
repeated by every client.

## The ask

The account response carries its opening balance: the transaction's id, `amount_cents` and
`date`, or `null` when the account has none. It is on `GET /v1/accounts`,
`GET /v1/accounts/{account_id}` and every write that returns an account, and stays true after the
row is edited or deleted through the transactions API.

## Done when

An account's response names its opening-balance transaction (id, amount, date) or says it has
none, matching what the transactions API holds, and the contract documents the field.

## What the CLI removes once it lands

Nothing is removed: the terminal client's account Edit form waits for this field before it shows
and changes an opening balance, instead of looking the row up with two extra reads.
