# A bank line split into several transactions keeps one identity, so a re-import recognises it

Raised 2026-10-15.

## Why

The owner splits one bank line into several transactions: a card charge of 100 becomes 60 of
groceries and 40 of household. Today a bank import recognises a line already in the ledger only
by its operation code, or by identical text, amount and date. Neither works on a split:

- the operation code sits on one part only, and card lines carry no code at all;
- no part has the line's amount.

So when a period is uploaded again, the split line is not recognised and is added a second time.
Every client that imports bank files or lets the owner split a line meets the same problem, and
only the engine sees every client's rows, so the rule belongs in the engine.

## The ask

1. **Every imported bank line gets an identity the engine keeps** — the operation code when the
   bank gives one, otherwise one the engine mints at import.
2. **Splitting a transaction keeps that identity on every part.** A split is one engine
   operation: one transaction in, several parts out, each with its own amount, category and
   hashtags, the parts summing to the original amount.
3. **An import matches a bank line to all its parts.** A line whose identity is already in the
   ledger is reported as already there, whether it is one transaction or several parts, and is
   not added again.
4. **Rows already split before this lands can be linked to one line afterwards.** The owner's
   spreadsheet holds purchases split into several rows with nothing linking them. A linking
   operation takes several existing transactions and gives them one identity, as if they had been
   split in the engine; it is refused with a structured error when the rows are on different
   accounts or already belong to another line. See "Rows split before this lands" below.
5. A part keeps the identity when it is edited; deleting every part frees it.

## Done when

- A line imported, split in two, and imported again is reported as already in the ledger, and the
  ledger still holds exactly the two parts.
- The same holds for a card line that came with no operation code.
- A split whose parts do not sum to the original amount is refused with a structured error that
  names the parts.
- Several existing transactions linked as one line are matched by a later bank file holding that
  line, and nothing is added.

## Rows split before this lands

The owner's spreadsheet is imported once, onto an empty ledger, and holds purchases already split
into several rows. Example: a card purchase of `WONG -100` on 3 October is two rows, `WONG -60`
and `WONG -40`, with no bank code on either.

Only the splits that a bank file can still reach matter. Once the owner completes a period's
reconciliation, the engine refuses new imported rows in that window, so older splits are safe.
For the recent, unreconciled weeks, this client proposes the plan below; the engine coders'
view decides it.

- **Proposed: link after import.** After the spreadsheet import, this client reads the bank
  download against the ledger and lists the fixes for the owner to approve, one of which is "these
  rows look like one purchase on the statement: link them?" Each approved link calls the linking
  operation in point 4 of the ask. The owner changes nothing in the spreadsheet.
- **Alternative: group at import.** The owner marks the parts in the spreadsheet (the same number
  on each part), and the import of past rows accepts a group marker per row, so the parts arrive
  already sharing one identity. This needs no linking operation, but the owner must find every
  split by hand first.

Questions for the engine coders:

1. Which of the two do you prefer, or is there a better way?
2. Is the identity one the engine always mints, or the bank's operation code when there is one?
3. When a split's parts no longer sum to the line (one part edited), what does a re-import do?

## What this client removes once it lands

Nothing to remove: today this client has no way to split a line, and a split line from the
spreadsheet is added a second time on re-import. Once it lands the client gains a split action
and links the spreadsheet's split rows as the engine coders choose above.
