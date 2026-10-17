# A bank line is reconciled whole: assigning or unassigning one part does the same to every part

Raised 2026-10-17.

## Why

A reconciliation checks the ledger against the bank statement, and the statement holds bank
lines, not the parts a user split them into. A charge of 100 split into 60 of groceries and 40 of
household is one movement on the statement, so it is either reconciled or not.

Today the engine reconciles part by part: `reconciliation_id` on `PUT /transactions/{id}`
settles `{id}` alone (contract: `PUT /transactions/{id}`, "Line fields"). So one part can sit in
a reconciliation while its sibling does not, and that mixed state then surfaces as refusals no
user can make sense of:

- a line field changed on one part is refused because of the other part ("Another part of this
  bank line (<id>) is the cause: Locked by completed reconciliation.");
- moving the line to another account is refused with `ASSIGNED_TO_RECONCILIATION` naming the
  other part;
- splitting the line again is refused with `SPLIT_RECONCILIATION_MIXED`.

Every client would have to explain these cases, and none of them reflects anything on the
statement. The owner's rule: reconciliation works on the whole purchase, never on one part.

## The ask

1. **`reconciliation_id` is a line field.** Sending it on `PUT /transactions/{id}` (to assign,
   move or unassign) writes it onto every live part of the line, in one write, the way `title`,
   `date`, `account_id` and `operation_code` already are. Every rule is checked on every part
   it would change, and nothing is written if one refuses.
2. **Every route that creates parts of one line gives them one reconciliation**: a split
   already does; a `line_group` in `POST /transactions/batch` does the same.
3. **Lines already in a mixed state are settled once** when this lands. The engine coders say
   how (for example: every part joins the reconciliation its siblings are in when there is only
   one, and the rest are reported).
4. Say which refusal reasons can no longer arise once a line is always wholly in or out of a
   reconciliation (`SPLIT_RECONCILIATION_MIXED`, and the "another part is the cause" messages
   that come from reconciliation), and retire them from the contract.
5. A reconciliation's figures and its `?reconciliation_id=` listing include every part of each
   line it holds.

## Done when

- Assigning one part of a 60 + 40 line to a draft reconciliation leaves both parts assigned to
  it; unassigning either part unassigns both.
- No line in any user's ledger has parts in different reconciliations, or some parts in one
  and others in none.
- Changing the date of a part whose line is in a completed reconciliation is refused as
  `LOCKED` for the line itself, never because of "another part".
- Completing a reconciliation that holds a split line counts the line's full total.

## What this client removes once it lands

Nothing yet: the client has not built split editing. Without this ask, the edit form of a part
needs its own screen to explain a refusal caused by another part, and the reconciliation screen
would let the owner tick half a purchase. With it, that screen is not built, and ticking a
purchase on the reconciliation screen ticks the whole purchase.
