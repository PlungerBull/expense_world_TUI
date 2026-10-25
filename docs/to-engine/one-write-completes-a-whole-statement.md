# One write completes or reverts a whole statement, both halves of a card

Raised 2026-10-24.

## Why

A card statement is two reconciliations (one per currency) that the person treats as one
statement: they order it once and then complete it. Today completing it takes two writes,
`POST /v1/reconciliations/{id}/complete` on each half, and reverting it takes two
`POST /v1/reconciliations/{id}/revert`. Neither pair is atomic. If the second write is refused
(the dollar half does not balance, or something changed meanwhile), the statement is left half
completed: one half locked with its statement lines showing, the other a draft without them.
Undoing that means another write, which can fail too.

Every client (this one, then web and iOS) would rebuild the same pair of writes and the same
"half completed" state to explain and recover from.

## The ask

1. **Completing a reconciliation completes its whole statement**: on an account with a statement
   code and a twin, both halves in one atomic write, or a new route for it if changing
   `POST …/complete` is not wanted. A reconciliation with no twin completes as today.
2. **The same for revert**: both halves back to draft in one write.
3. **All or nothing.** If either half is refused (not balanced, not ordered, not a draft), nothing
   is written, and the refusals of both halves come back together, each naming its
   reconciliation.
4. **The answer** holds both reconciliations as they are after the write. An idempotent replay
   answers exactly as the first request did.

## Done when

- Completing a card statement whose two halves balance and are ordered completes both in one
  write, and every line of both shows its statement line.
- Completing one whose dollar half does not balance writes nothing: both halves stay drafts, and
  the refusal names the dollar half.
- Reverting a completed card statement turns both halves back to draft in one write.
- A reconciliation on an account with no statement code, or with no twin, completes and reverts
  as today.
- A replay with the same idempotency key answers as the first request did.

## What this client removes once it lands

Completing or reverting a card statement is one write: no second write after the first, no
"one half completed" state to show, and no recovery step when the second write fails.
