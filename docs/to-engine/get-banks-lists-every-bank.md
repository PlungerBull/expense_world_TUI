# GET /banks lists every bank the owner's accounts were at

2026-11-13

## Why

A bank account is made from a bank the engine lists, and the engine names it from that bank and
its last 4 (`BCP-5678`). The engine lists one bank, BCP. The owner's ledger also holds two closed
accounts at **Interbank**, which the official import brings in from the owner's spreadsheet and
then archives. Today they can't be made as bank accounts, so they would have to be made people,
which they are not. Every client would meet the same gap with any owner who banked elsewhere.

## The ask

- `GET /banks` lists **Interbank** beside BCP, with whatever a listed bank carries (its code and
  its display name, as BCP has), so a bank account can be made at it and named from it
  (`INTERBANK-1234`).
- A bank account at Interbank behaves as one at BCP: it holds its currencies and its opening
  balances, takes the sheet import's rows, and archives.
- Nothing else changes for BCP or its accounts.

## Done when

- `GET /banks` lists Interbank.
- `POST /accounts` with Interbank and a last 4 makes an account named `INTERBANK-<last 4>`; two
  such accounts with different last 4s both exist.
- The sheet import puts rows on an Interbank account by its id, as on a BCP one, and the account
  archives once its rows are in.

## What this client removes once it lands

Nothing to remove: the client lists whatever `GET /banks` returns. The official import's rehearsal
and the owner's import wait on it, since the two closed Interbank accounts can only be made once
Interbank is listed.
