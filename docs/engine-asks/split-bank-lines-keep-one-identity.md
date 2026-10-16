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
4. **An import of past rows can say which rows are parts of one line**, so a split made outside
   the engine (in the owner's spreadsheet) comes in already grouped.
5. A part keeps the identity when it is edited; deleting every part frees it.

## Done when

- A line imported, split in two, and imported again is reported as already in the ledger, and the
  ledger still holds exactly the two parts.
- The same holds for a card line that came with no operation code.
- A split whose parts do not sum to the original amount is refused with a structured error that
  names the parts.
- Past rows sent as one group import as the parts of one line, and a later bank file holding that
  line matches them.

## What this client removes once it lands

Nothing to remove: today this client has no way to split a line, and a split line from the
spreadsheet is added a second time on re-import. Once it lands the client gains a split action
and groups the spreadsheet's split rows on import.
