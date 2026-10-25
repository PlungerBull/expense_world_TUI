# One write completes or reverts a whole statement, both halves of a card

Raised 2026-10-24; revised 2026-10-24 with the engine coders' corrections: a non-zero difference
is not a refusal, refusals come one check at a time, and the existing routes change rather than a
new one being added.

## Why

A card statement is two reconciliations (one per currency) that the person treats as one
statement: they order it once and then complete it. Today completing it takes two writes,
`POST /v1/reconciliations/{id}/complete` on each half, and reverting it takes two
`POST /v1/reconciliations/{id}/revert`. Neither pair is atomic. If the second write is refused
(the dollar half has no ending balance, say, or something changed meanwhile), the statement is
left half completed: one half locked with its statement lines showing, the other a draft without
them. Undoing that means another write, which can fail too.

Every client (this one, then web and iOS) would rebuild the same pair of writes and the same
"half completed" state to explain and recover from. A second route beside today's would still
leave half completing reachable through the old one, so the existing routes change.

## The ask

1. **`POST …/complete` on either half of a card statement completes both halves** in one atomic
   write. A reconciliation with no twin, or on an account without a statement code, completes as
   today.
2. **`POST …/revert` does the same**: both halves back to draft in one write.
3. **Per half, a half already in the asked state is left as it is**, as completing a completed
   reconciliation does nothing today: completing the statement completes whichever half is still
   a draft, and reverting it reverts whichever half is completed.
4. **All or nothing, one check at a time.** Each check runs on both halves before the next check
   runs. The first check that fails answers, naming every half it failed on, and nothing is
   written. A non-zero difference stays allowed, as today.
5. **The answer** holds both halves as they are after the write. An idempotent replay answers
   exactly as the first request did.

This changes the complete and revert answers for every client; this client is the only one built
so far and takes the change.

## Done when

- Completing either half of a card statement whose two halves are ordered completes both in one
  write, and every line of both shows its statement line.
- Completing one whose dollar half has no ending balance writes nothing: both halves stay drafts,
  and the refusal names the dollar half.
- Completing one where both halves have no ending balance writes nothing, and the one refusal
  names both halves.
- Completing a statement whose soles half is already completed completes the dollar half and
  leaves the soles half as it is.
- Reverting either half of a completed card statement turns both halves back to draft in one
  write.
- A reconciliation on an account with no statement code, or with no twin, completes and reverts
  as today.
- A replay with the same idempotency key answers as the first request did.

## What this client removes once it lands

Completing or reverting a card statement is one write: no second write after the first, no
"one half completed" state to show, and no recovery step when the second write fails.
