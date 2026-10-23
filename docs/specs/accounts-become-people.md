# Turn an account into a person, and back

**Status: approved (owner, 2026-10-22).** The engine half is the engine repo's spec
`account-kind-conversion.md`, shipped 2026-10-21; this is the TUI half.

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
4. Importing the sheet, converting ALEJO PEN to a person, then running the import again with
   `--apply` creates no account (`Accounts: created 0`), and no row fails.

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

**Questions for the owner:** none open.

## Tasks

Approved by the owner 2026-10-22, who picks 1 A · 2 A · 4 B · 5 B in
[expense-world-account-to-person.html](../mockups/expense-world-account-to-person.html), and
checks the import re-run on `--apply`: the dry run stays offline.

All three tasks are done, and the tester's acceptance check passed everything this spec owns.
Its librarian sweep and reply wait for [case-counts-in-codes.md](case-counts-in-codes.md) to
record contract `996986490b68f05e`, which the check found moved.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `56a43798fc1f2915` (exclusive) to `fab230c456c2dba2` (inclusive), the
  account half of the hand-off named above; its other half has its own reply,
  [caught-up-54fd1012f7d60abc.md](../to-engine/caught-up-54fd1012f7d60abc.md). The version the
  owner quotes for the next catch-up is the newest one, `996986490b68f05e`, from
  [case-counts-in-codes.md](case-counts-in-codes.md).
- **Done when, checked:** the two engine's checks above, with the tester's results.
- **Contract problems found:** what the build and the tester's run find, and one silence: the
  contract does not say what becomes of an account's reconciliations when it becomes a person,
  while a client offers reconciliations only on real accounts.
- **Asks this closes:** none.
