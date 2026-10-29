# What the statement screens' catch-up turned up

Small things part 1b of the cards and statements catch-up turned up, done on 2026-10-28 at
contract `e020782e3579d011`: the statement screens on the engine's statement routes. The rest of
what part 1b found already belongs to other specs: the dropped routes' words and citations, and
`t` on a holder, to [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md)
and todo.md's backlog item for the holder specs; a card with no statement code, to
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md);
the edit-part mockup's refusal, to [catch-up-leftovers.md](catch-up-leftovers.md).

**Status: draft, written 2026-10-28 for the owner to rewrite or approve, with two questions.** Its
tasks are drafted when the owner approves it. It runs after
[catch-up-cards-statements-2c-live-suite-holder-move.md](catch-up-cards-statements-2c-live-suite-holder-move.md),
so the catch-up's own parts come first. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **A holder of three accounts or more can't open a statement from the card form.** The form
  shows two accounts, the one it is opened on and one other. A holder of three currencies needs a
  balance for each, so the engine refuses the statement with `HOLDER_ACCOUNTS_MISSING`
  (contract: POST /v1/statements).
- **The one-account New statement form sends one balance**, even for an account whose holder
  holds two. Only the tests open that form on its own today.
- **The `⚑` count right after a close can read one too many.** It counts the close's
  `review_lines` on every balance, and a line flagged on two accounts is counted twice, until
  the flagged screen has read the engine's count (`GET /bank-lines/count?unassigned_in_period_of=`).
- **The flagged screen's head is blank while its first page loads.**
- **Leftover code and test words:** the read of bank lines by their ids keeps a `sort` option
  and a paragraph on ordering that no code uses; the flagged-lines test's fake engine checks that
  no `ids` are sent inside a step whose failure becomes a toast, so a regression shows as a
  timeout, not as a clear failure; some unit tests quote engine words not checked against the
  engine (a missing bank line written two ways, the zero-amount refusal, the sealed-line words
  citing the wrong write, test names that still say reconciliation); and one test sends
  `places` to the old `PUT /reconciliations/{id}/statement-order`, a route the engine no longer
  has, with a dead citation.

## What it must do

1. **A holder of three accounts or more** gets a statement as question 1 decides.
2. **No form sends one balance for a holder of two accounts or more.**
3. **The `⚑` count after a close is the engine's count.**
4. **The flagged screen's head** shows as question 2 decides.
5. **The code and tests above lose their leftovers:** no unused options or paragraphs, the
   `ids` check fails clearly, every engine sentence a unit test quotes is the engine's own, and no
   test sends to a route the engine no longer has.

## How the owner knows it is done

1. On a holder of three accounts, a statement opens as question 1 picks.
2. Right after a close that flags a line on two accounts, `⚑` shows the same count as the flagged
   screen.
3. The unit suite and the drift check pass.

## Questions for the owner

1. **A holder of three accounts or more and the card form.**
   - **A.** Leave it to part 7, which redraws the card's statement with a balance for each
     currency; until then the engine's refusal shows as it does today.
   - **B.** Fix the form now, with a mockup to pick first.

   **Recommended:** A. Part 7 already redraws this form, so a fix now would be drawn twice.
2. **The flagged screen's head while its lines load.**
   - **A.** Show the count as soon as the engine sends it, before the lines arrive.
   - **B.** Leave it blank until the first page arrives, as today.

   **Recommended:** A. The head shows sooner, and it is still the engine's count.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
