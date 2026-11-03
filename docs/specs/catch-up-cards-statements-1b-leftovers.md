# What the statement screens' catch-up turned up

Small things the statement screens' catch-up (contract `e020782e3579d011`) turned up. The rest of
what it found belongs to other specs: the dropped routes' words and citations, to
part 1, the app's reads and writes (done on 2026-10-30) and
todo.md's backlog item for them; `t` on an account, to
part 6 of the currencies catch-up, the main views (done on 2026-10-31); an account with no
statement code, and the New statement form, to
part 7 of the currencies catch-up (done on 2026-11-03); the
edit-part mockup's refusal, to the bank download and closing catch-up's leftovers (done on
2026-11-03).

**Status: approved on 2026-11-03; question 1 answered (A).** It waits on no other spec. When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

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

   **Picked:** A.

---

## Tasks

2. **The PDF upload's result counts with the engine.** The apply in
   [statement_upload.py](../../expense/tui/screens/statement_upload.py) (`_ask`) reads the
   engine's count of the completed statement's review list for the result screen's `⚑` line and
   `f`, not `len(review_line_ids(...))`; `review_line_ids` in
   [statement.py](../../expense/bank_import/statement.py) goes if nothing else uses it. Unit
   tests through the upload: a close whose `review_lines` sum differs from the engine's count
   shows the engine's count; a count of 0 shows no `⚑`; a failed count read toasts.
3. **The flagged lines' screen shows its head as soon as the count arrives.** `_load` in
   [reconciliations.py](../../expense/tui/screens/reconciliations.py) reads the engine's count
   first and paints `flagged_head` with it, then reads and paints the lines; the head's words are
   unchanged. A unit test holds the lines' read and finds the head painted with the count.
4. **Code leftovers.** `fetch_bank_lines_by_ids` in [reads.py](../../expense/reads.py) loses its
   `sort` option and the paragraph on ordering; the flagged-lines test's fake engine
   ([test_tui_flagged_lines.py](../../tests/unit/test_tui_flagged_lines.py)) fails with a clear
   assertion, not a timeout, when `ids` are sent; the `statement-order` case and test in
   [test_no_read_only_fields.py](../../tests/unit/test_no_read_only_fields.py) go or move to a
   route the engine has, with a citation the live contract holds.
5. **Every engine sentence a unit test quotes is the engine's own.** The quotes "Why" names (a
   missing bank line, the zero-amount refusal, the sealed-line words and the write they cite)
   are checked against the practice engine and corrected, and test names that still say
   reconciliation say statement.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
