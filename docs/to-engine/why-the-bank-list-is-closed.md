# The engine says why its bank list is closed, and whether a bank and a sheet's accounts can come from the user

2026-11-13

## Why

`GET /banks` lists one bank, BCP, the same for every user, and a bank account must be at a listed
bank (contract: GET /v1/banks). The owner's spreadsheet also holds two closed accounts at
Interbank, so the official import waits on the ask "GET /banks lists every bank the owner's
accounts were at". That ask adds one bank; the next owner who banked elsewhere waits on another.

The owner would rather the import read the sheet and ask: a sheet account the ledger does not
hold (`IBK`, say) is offered as an account to make, at the bank its name suggests (Interbank),
for the owner to confirm or pick another bank, adding it when it is not there. Today the sheet
import makes no account (contract: POST /v1/transactions/import-sheet, "Names"), so every account
is made by hand first. Before this client asks for that, it needs the engine's reasons.

## The ask

Answer each, in the hand-off:

1. **Why is the bank list fixed and the same for every user?** What does a listed bank carry or
   enable beyond its code and name: reading its statement PDFs, its bank downloads, its statement
   codes, anything else?
2. **Can a user add a bank** (a code and a name) so accounts are made at it and named from it
   (`INTERBANK-1234`), with whatever is bank-specific, such as reading its PDFs, simply not
   offered at it? If not, what breaks?
3. **Is "the sheet import makes no account" a rule the engine holds for a reason,** or only how
   it was built?
4. **Could the sheet import propose the accounts it is missing:** for each sheet account name no
   account holds, a kind, a bank guessed from the name (by names a bank is known by, `IBK` for
   Interbank) and the currencies its rows use, for the client to show and the user to confirm,
   change or refuse, the confirmed ones made in one write before the import? The guess would be
   the engine's, so every client offers the same one.

## Done when

- Each of the four is answered in the engine's hand-off.
- Where the answer is "it can change", the hand-off says whether the engine plans it, so this
  client can replace the ask "GET /banks lists every bank the owner's accounts were at" with one
  for that change.

## What this client removes once it lands

Nothing yet: this is a question. If a user can add a bank and the import proposes its missing
accounts, this client drops making every sheet account by hand before the import and naming each
bank account's sheet name on the command line, and the Interbank ask is withdrawn.
