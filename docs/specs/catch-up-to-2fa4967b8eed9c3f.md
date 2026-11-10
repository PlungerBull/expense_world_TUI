# The app on contract 2fa4967b8eed9c3f: an account's kind, strict requests and the closed-day refusals

Catches up to contract `cd6574eee1dd5ec0` through `2fa4967b8eed9c3f`, everything in the engine's
hand-off "A closed day never holds a line in no statement, every request value the engine does not
accept is refused with its own reason, and an account says its kind, cash included" (2026-11-08)
but two pieces of screen work: the cash account's screens, which
are built, and resolving leftover lines before a close,
which [closing-with-leftover-lines.md](closing-with-leftover-lines.md) takes. It runs first:
until it lands, the live contract suite cannot run on the engine.

**Status: approved on 2026-11-08.** When done, the
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

Every task is done; the acceptance check, the doc sweep and the reply follow.

## Reply to the engine

Part 1 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"), covering `cd6574eee1dd5ec0` to `2fa4967b8eed9c3f` but its cash screens and the
resolving of loose lines (parts 2 and 3, in the two specs named above). It reports on the
hand-off's "Done when" checks for an edit sending only changed fields, no request refused
`INVALID_FORMAT` or `BODY_NOT_ACCEPTED`, `ACCOUNT_ARCHIVED` shown, every answer read by `kind`,
`kind` sent on create and `SEALED_PERIOD` shown, and any contract problem found.

## Found along the way

Not built in this spec; sorted when it is done.

- **A bank account made on the New form sent a typed `name`,** which the engine refuses
  (`NAME_BUILT`); the New form now sends the bank and last 4, so check 3 can prove a bank
  account made too.
- **`scripts/clean_practice_user.py` read `is_person`;** task 1 moved it to `kind`, since the
  cleaner would fail on the new engine.
- **Some unit tests build dashboard rows by hand without `kind`** (test_tui_bracketed_names.py,
  test_tui_home_dispatch.py, test_tui_home_header.py), and test_tui_smoke.py's sample rows keep an
  old flat shape (no `id`, no `currencies`); Home reads neither, so nothing fails.
- **`ACCOUNT_ARCHIVED` keyed `opening_balances.<code>`** on `PUT /accounts/{id}` now reaches the
  account Edit form, which saves in one write and shows it on that currency's line.
- **The sheet import's `--create-names` sends no `kind`** (expense/import_/engine.py
  `_create_body`), the one `POST /accounts` task 1 missed; it also sends a typed `name`, which a
  bank account no longer takes. [The official import](before-the-official-import.md) rewrites that
  step for built names, so it takes `kind` with it.
