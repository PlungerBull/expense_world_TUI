# Turn an account into a person, and back

**Status: draft (owner, 2026-10-21).** The engine half is the engine repo's spec
`account-kind-conversion.md`; the TUI half
waits for it to land.

---

## Why

The spreadsheet now records loans the way the app does: every movement with a person is
mirrored in an account named after that person, and the account's balance is the debt. The
sheet has eight such accounts: ALEJO, ALONSO, LC, ALEX, LIDIA, MATILDE, CARLOS and KORAKUEN.
Four of them hold both soles and dollars, so they become twelve accounts in the app.

The sheet import creates every sheet account as a bank account. Rather than teach the import
which names are people, the owner turns an account into a person in the app: a plain account
action, useful again whenever an account was created as the wrong kind.

## What it must do

- From the Accounts screen, the owner turns a bank account into a person, or a person back
  into a bank account. History, balance, name and currency stay as they are; the account only
  moves between the banks and the people groups (on Accounts and on Home).
- When the engine refuses, the reason is shown in the engine's words. A person cannot carry an
  opening balance, so a bank account with one cannot become a person until it is removed.
- The screen change is drawn as a mockup and picked by the owner before it is built.
- **The sheet import finds people too.** When it looks up which accounts already exist, it
  includes people, so re-running the import after a conversion reuses the person account
  instead of trying to create the name again and failing those rows.

## How the owner knows it is done

1. A bank account with transactions becomes a person: it shows under people with the same
   balance and history, and the transactions screen still lists its rows.
2. The same person turns back into a bank account the same way.
3. A bank account with an opening balance is refused with the engine's reason, and nothing
   changes.
4. Importing the sheet, converting ALEJO PEN to a person, then running the import's dry run
   again shows ALEJO PEN as reused, not as a new account, and no row fails.

## Catching up with the engine

**Catches up to contract `fab230c456c2dba2`:** every contract change after `56a43798fc1f2915`
up to it, the account half of the engine's hand-off "Every bank line carries an engine-given
code and an optional statement-line reference, and an account can become a person and back"
(shipped 2026-10-21). Its line-code and statement-line half is built, up to contract
`54fd1012f7d60abc` ([decisions.md](../decisions.md) "The sheet import brings a split purchase in
as one split transaction").

**The engine's checks** — its "Done when" for this half. The tester's acceptance check runs them,
and the reply reports each result.

1. A real account becomes a person and back from the Accounts screen, and each refusal shows its
   reason.
2. A sheet-import re-run after a conversion finds the converted account and creates no duplicate.

**What the engine declined:** nothing; the hand-off answers no ask. Its note that a sheet account
seeded by a `SALDO INICIAL` row cannot become a person until that opening balance is deleted
needs nothing here: the sheet's only opening balance is PARDO's, which stays a bank account
([before-the-official-import.md](before-the-official-import.md)).

**Questions for the owner:** the screens, in todo.md "How an account becomes a person on screen",
and "The dry run cannot tell a reused account" there, on the owner's check 4 above.

## Tasks

Drafted 2026-10-21; wait for the owner's approval. Task 1 draws nothing; task 2 waits for the
picks; task 3 waits for the answer on check 4.

1. **The live contract tests know both routes.** A real account with transactions becomes a
   person (`POST /accounts/{id}/make-person`): `200`, `is_person` true, balance, name, currency
   and transactions unchanged, `version` up by one, listed among the people by
   `GET /accounts?include_people=true` and in `/dashboard`'s `people`, `sort_order` the next one
   at the end of the people; `make-account` turns it back the same way. Refused with `409` on
   `account_id`, nothing written: `KIND_UNCHANGED` on each route, `HAS_OPENING_BALANCE` on
   `make-person` (and it goes through once the opening balance is deleted), and
   `ACCOUNT_ARCHIVED` on both for an archived account and an archived person, checked first. An
   unknown id is `404`. A replay with the same idempotency key does not flip it twice.
2. **Manage ▸ Accounts turns an account into a person and back,** as the picked screens draw,
   through the two routes, and shows `KIND_UNCHANGED`, `HAS_OPENING_BALANCE` and
   `ACCOUNT_ARCHIVED` in the engine's words (with the app's line, if screen 4 B is picked); Home
   shows it in its new group. Unit tests: both directions, the cursor after, each refusal.
   [tui.md](../tui.md) says what the key or the line does. Passes the owner's checks 1 to 3 and
   the engine's check 1.
3. **The sheet import finds people.** It lists existing accounts with
   `GET /accounts?include_people=true&include_archived=true`, so a person account of the same
   name and currency is reused and never created again. Unit test: a re-run after a conversion
   creates no account and fails no row; the check the owner reads, on the dry run or on
   `--apply`, follows the answer on check 4. Passes the owner's check 4 and the engine's check 2.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `56a43798fc1f2915` (exclusive) to `fab230c456c2dba2` (inclusive), the
  account half of the hand-off named above; its other half has its own reply,
  [caught-up-54fd1012f7d60abc.md](../to-engine/caught-up-54fd1012f7d60abc.md), whose version,
  `54fd1012f7d60abc`, is the one the owner quotes for the next catch-up.
- **Done when, checked:** the two engine's checks above, with the tester's results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
