# A bank line's edit limits say why each field is locked, in words

Raised 2026-10-25.

## Why

`GET /v1/bank-lines/{bank_line_id}` returns `edit_limits`, and each entry of `locked_fields` and
`locked_part_fields` carries the reason the write would give, as a code only: `LOCKED`,
`ACCOUNT_ARCHIVED`, `OPENING_BALANCE_ACCOUNT_FIXED`, `SPLIT_TOTAL_MISMATCH`. The terminal
client shows those fields read-only before anyone types, and the owner wants each read-only
field to say why, e.g. "its reconciliation is completed", for every reason the engine gives.

A code alone means every client keeps its own table from code to sentence: four copies of the
same words, drifting apart, and a new reason added by the engine shows nothing in any client
until each one adds it. The engine's refusals already carry their words in `message`; the limits
that predict those refusals should carry words too.

## The ask

Each locked field in `edit_limits` (both `locked_fields` and each part's `locked_part_fields`)
carries a short sentence a client can show beside the field as is, next to the code it carries
today. The sentence says why the field cannot change, in words a user reads, the same for every
client (e.g. for `LOCKED`, that the line's reconciliation is completed; for `ACCOUNT_ARCHIVED`,
that its account is archived; for `OPENING_BALANCE_ACCOUNT_FIXED`, that an opening balance stays
on its account). The engine picks the shape: an object per field with its code and its words, or
a sibling map of words keyed like the codes, whichever keeps the contract clearest. The live
contract states the shape and the words for each reason.

## Done when

- Every field `edit_limits` names comes with its code and a sentence, for each reason it can
  give, on a line's own fields and on its parts' fields.
- The live contract (`GET /v1/bank-lines/{bank_line_id}`, "Response fields") describes the
  sentence beside the code.

## What this client removes once it lands

Nothing to remove: without the sentence, the client shows a bare "read-only" and holds no table
of its own. Once it lands, the Edit form shows the engine's sentence beside each read-only field.
