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

## Tasks

None yet: drafted once the engine has landed the ask and the mockup is picked.
