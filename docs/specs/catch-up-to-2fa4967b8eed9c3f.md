# The app on contract 2fa4967b8eed9c3f: an account's kind, strict requests and the closed-day refusals

Catches up to contract `cd6574eee1dd5ec0` through `2fa4967b8eed9c3f`, everything in the engine's
hand-off "A closed day never holds a line in no statement, every request value the engine does not
accept is refused with its own reason, and an account says its kind, cash included" (2026-11-08)
but two pieces of screen work: the cash account's screens, which
[the-cash-account.md](the-cash-account.md) takes, and resolving leftover lines before a close,
which [closing-with-leftover-lines.md](closing-with-leftover-lines.md) takes. It runs first:
until it lands, the live contract suite cannot run on the engine.

**Status: draft, 2026-11-08, for the owner to approve.** It has no open question. When done, the
why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live engine already runs `2fa4967b8eed9c3f`, and three of its changes break the app today:
Home's account list reads a key the engine renamed (`bank_accounts` is now `accounts`), people
read as bank accounts because `is_person` left every answer for `kind`, and a new account is
refused because `kind` is now required. The engine also refuses, with a reason of its own, request
values it used to take loosely, and a few writes on closed days.

## What it must do

1. **Every account is told apart by its kind** (bank, person or cash), never by `is_person` or
   by name; every new account says its kind.
2. **Home's balances come back,** looking as they do today.
3. **The engine's new refusals show in its words:** an unassign, a draft delete or an upload
   refused because the day is closed names the statement that closes it; an archived account's
   opening balance or new currency says to unarchive it first. None of them is retried.
4. **An edit sends only what changed,** so an unchanged locked field never refuses a save.
5. **No request the app sends is refused for its shape** (a true/false, a number, a body where
   none belongs).
6. **The live contract suite runs on the new engine** and proves each of these.

## How the owner knows it is done

1. Home lists the bank accounts and people with today's balances, as before.
2. Manage ▸ Accounts shows each person as a person and each bank account as a bank account.
3. Creating a bank account or a person works.
4. Unassigning a line on a closed day shows the engine's message naming the statement.
5. Editing an archived account's opening balance shows the engine's "unarchive it first".
6. The tester runs the live contract suite against the practice engine, green.

## What the engine declined, or did differently

- **The cash account is made only when asked:** no user holds one until a client creates it
  (`POST /accounts`, `kind: "cash"`); the engine never makes it on its own.
- **A locked field sent unchanged inside a completed statement is still refused** (`LOCKED`);
  only outside a completed statement is an unchanged value let through.
- **The two open questions it settled:** what may change on a line on a closed day (the state no
  longer exists), and an archived account's opening balances (one `ACCOUNT_ARCHIVED`).

---

## Tasks

Drafted 2026-11-08. Each reads the live contract on the practice engine before building.

1. **The account's kind in the app.** Every account read takes `kind` (`bank`, `person`,
   `cash`); `is_person` is read only from activity entries written before the change
   (expense/reads.py, the accounts, statements and create-form screens,
   expense/bank_import/flow.py). The New form and every `POST /accounts` send `kind` (`bank` or
   `person`), never `is_person`. The unit fake engine (tests/unit/helpers.py) answers with
   `kind`.
2. **The live suite on `kind`.** The contract helpers (tests/contract/conftest.py and every test
   making an account) send `kind`; the suite's account reads take `kind`. Passes when the suite
   runs on the practice engine with no `REQUIRED` or `UNKNOWN_FIELD` on `kind`/`is_person`.
3. **Home reads `/dashboard`'s `accounts`.** Its balance block, and every other reader of
   `/dashboard`, read `accounts` in place of `bank_accounts`; the look is unchanged.
4. **The new refusals in the engine's words.** `SEALED_PERIOD` from `space` on a statement's
   checklist, the Edit form's statement change, a draft's delete and an upload;
   `ACCOUNT_ARCHIVED` from an opening-balance edit and a currency add, on their line. A unit test
   each, and a test that `expense/http.py` retries neither `SEALED_PERIOD` nor
   `LOOSE_LINES_ON_SEALED_DAYS`.
5. **Strict requests, proven.** Unit tests that every body true/false the app sends is JSON
   `true`/`false`, every number a JSON number, every query flag exactly `true`/`false`, no body on
   an operation that takes none (archive, unarchive, every `GET` and `DELETE`), and any
   `sort_order` within ±1,000,000,000. An edit inside a completed statement sends no locked field,
   and an unchanged `date` is not sent. Anything found wrong is fixed.
6. **The live contract tests:** `kind` on every account answer and on `GET /activity` snapshots;
   `POST /accounts` without `kind` (`REQUIRED`), with `is_person` (`UNKNOWN_FIELD`), with a
   wrong kind (`INVALID_FORMAT`); `/dashboard`'s `accounts` with `kind`; `"true"` and `1` for
   `dry_run` and `"5"` for `sort_order` (`INVALID_FORMAT`); `1` for a query flag
   (`INVALID_FORMAT`); `{}` sent to archive (`BODY_NOT_ACCEPTED`); `sort_order` past the bound
   (`OUT_OF_RANGE`); `ACCOUNT_ARCHIVED` on the three account routes; `SEALED_PERIOD` on an
   unassign and a draft delete; an unchanged `date` let through on a closed day outside a
   completed statement and `LOCKED` inside one.

## Reply to the engine

Part 1 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"), covering `cd6574eee1dd5ec0` to `2fa4967b8eed9c3f` but its cash screens and the
resolving of loose lines (parts 2 and 3, in the two specs named above). It reports on the
hand-off's "Done when" checks for an edit sending only changed fields, no request refused
`INVALID_FORMAT` or `BODY_NOT_ACCEPTED`, `ACCOUNT_ARCHIVED` shown, every answer read by `kind`,
`kind` sent on create and `SEALED_PERIOD` shown, and any contract problem found.

## Found along the way

Not built in this spec; sorted when it is done.
