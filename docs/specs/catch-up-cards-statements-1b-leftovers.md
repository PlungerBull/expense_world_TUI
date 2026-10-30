# What the statement screens' catch-up turned up

Small things the statement screens' catch-up (contract `e020782e3579d011`) turned up. The rest of
what it found belongs to other specs: the dropped routes' words and citations, to
[catch-up-currencies-1-reads-and-writes.md](catch-up-currencies-1-reads-and-writes.md) and
todo.md's backlog item for them; `t` on an account, to
[catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md); an account with no
statement code, and the New statement form, to
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md); the
edit-part mockup's refusal, to [catch-up-leftovers.md](catch-up-leftovers.md).

**Status: draft, written 2026-10-29 for the owner to rewrite or approve, with one question.** Its
tasks are drafted when the owner approves it. It runs after
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md), which
redraws the statement screens it touches. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **The `⚑` count right after a close can read wrong.** It is the app's own sum of the close's
  `review_lines`, one list per currency the statement covers, until the flagged screen has read
  the engine's count (`GET /bank-lines/count?unassigned_in_period_of=`). A close also flags lines
  in a currency the statement holds no balances for, under `not_covered[].review_lines`
  (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`"), a second source the
  sum has to reach. The app takes the count in two places: the statement screen's close and the
  PDF upload's.
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

1. **The `⚑` count after a close is the engine's count,** in every currency, the ones the
   statement does not cover included.
2. **The flagged screen's head** shows as question 1 decides.
3. **The code and tests above lose their leftovers:** no unused options or paragraphs, the
   `ids` check fails clearly, every engine sentence a unit test quotes is the engine's own, and no
   test sends to a route the engine no longer has.

## How the owner knows it is done

1. Right after a close that flags lines in two currencies, one of them a currency the statement
   holds no balances for, `⚑` shows the same count as the flagged screen, after a statement's
   close and after a PDF upload alike.
2. The unit suite and the drift check pass.

## Questions for the owner

1. **The flagged screen's head while its lines load.**
   - **A.** Show the count as soon as the engine sends it, before the lines arrive.
   - **B.** Leave it blank until the first page arrives, as today.

   **Recommended:** A. The head shows sooner, and it is still the engine's count.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
