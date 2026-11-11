# Closing a month with leftover lines

Part of the catch-up to contract `2fa4967b8eed9c3f` (the engine's hand-off of 2026-11-08,
part A, 1 to 3): resolving lines in no statement before a close.

**Status: approved on 2026-11-08, its questions answered on the mockup
[expense-world-leftover-lines.html](../mockups/expense-world-leftover-lines.html); question 4
answered on 2026-11-11. The app reads the refusal's `details` (`EngineError.details`).** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Once a month's statement is completed, every line dated on its closed days is in a statement: a
line left over is wrong by definition, not something to review after the close. The engine now
refuses a close, and a statement PDF's upload (its preview too), while a line in no statement sits
on a day the close seals. The owner deals with each line first: fixes it so the paper takes it,
moves it, puts it in a statement, or deletes it.

## What it must do

1. **A close or an upload refused for leftover lines lists them,** read from the engine, and lets
   the owner deal with each one and close again, without leaving the screen.
2. **Nothing tells the owner to clean up a line on a closed day after closing.** Only the month's
   last day stays open until the next month closes; a line there is still flagged after the close.
3. **The upload preview's flagged lines say they sit on the last day.**

## How the owner knows it is done

1. A PDF whose month holds a line in no statement is refused before the preview; the app lists
   the line, and fixing it to the paper's row, moving it or deleting it, then reading the paper
   again, opens the preview, and the month closes.
2. `c` on a statement closed by hand, refused for a leftover line, lists it; putting it in the
   statement, then closing again, closes the month.
3. No screen tells the owner to clean up a flagged line on a closed day after the close.
4. A line on the paper's last day shows in the preview as one the close will flag, worded as
   staying open until the next month closes.

## What the engine declined, or did differently

- **The days a close seals:** every day of the statement but its last; the last day too once the
  next statement is completed; and the previous statement's last day, once that is completed and
  ends the day before. A line on a day that stays open (the last day, a gap between statements)
  is flagged, not refused.
- **A line taken out by the upload counts as in no statement,** so a paper that leaves out a line
  of the draft on a sealed day is refused for it too.
- **Refused, never a conflict:** a write and a close that would seal its day happen one after the
  other; whichever comes second is refused, never retried.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | A PDF refused for leftover lines? Mockup pane 1. | A: a screen listing them, `⏎` edits, `d` deletes, `r` reads the paper again (2026-11-08). |
| 2 | `c` refused on a statement closed by hand? Mockup pane 2. | A: the same screen, plus `space` to put a line in the statement and `c` to close again (2026-11-08). |
| 3 | The preview's "⚑ Will be flagged" block? Mockup pane 3. | A: kept, reworded for the last day (2026-11-08). |
| 4 | A refusal naming more than 200 lines? Mockup pane 4. | A: the screen's head gives the full count and says the first 200 are listed (2026-11-11). |
| 5 | Every leftover line dealt with? Mockup pane 5. | A: `Nothing is left over: r reads the paper again.`, `⏎` and `d` leave the footer (2026-11-11). |
| 6 | The head's count after a fix or delete? Mockup pane 6. | A: it counts what is listed; past 200 it keeps the engine's full count until `r` (2026-11-11). |
| 7 | The line under the head? Mockup pane 7. | A: `Nothing was written.`, as every refused file (2026-11-11). |
| 8 | The month in the head, which the refusal does not name? | Ship `Can't close the statement yet` now; the month comes with the engine ask "A loose-lines refusal names the statement it would close" (2026-11-11). |
| 9 | A line fixed with `⏎` and saved? | The screen sends the paper again as a dry run at once, as `r` does: a fixed line leaves, and with nothing left the preview opens (2026-11-11). A deleted line leaves on the list's fresh read. |
| 10 | `Nothing was written.` after a delete on the screen? | Kept: it speaks of the paper (2026-11-11). |
| 11 | `space` on the screen from `c`? | The line leaves the list on its fresh read, which says the statement each line is in (2026-11-11). |
| 12 | A line fixed with `⏎` on the screen from `c`? | It stays listed until `c`; once the engine ask "A close can be checked before it is sent" lands, a fix checks the close at once, as on the upload's screen (2026-11-11). |
| 13 | Every line dealt with on the screen from `c`? | `Nothing is left over: c closes <statement>.`; `⏎`, `space` and `d` leave the footer (2026-11-11). |

---

## Tasks

Approved; question 4 on 2026-11-11. Each reads the live contract on
the practice engine before building.

2. **The same screen from `c`** (questions 2, 11–13, and 6, 7 and 10 as on the upload's screen;
   stopped part-built on 2026-11-11, its code uncommitted in the working copy, unreviewed):
   opened by the refusal on `POST /statements/{id}/complete`, its lines from `details` as in
   task 1, its head naming the statement; `space` puts the line in the statement, `c` asks
   "Complete statement?" again.
3. **The month in the head** (question 8; waits on the engine ask "A loose-lines refusal names
   the statement it would close"): the head reads `Can't close <the statement's name> yet` from
   `details`, on the upload's screen.
4. **The live contract tests:** `LOOSE_LINES_ON_SEALED_DAYS` on a close and on an upload's dry
   run and apply, nothing written; the refusal's `details` ids in the order
   `?unassigned_in_period_of=<id>&sort=statement` lists them; the line taken out of the draft
   counted; 201 loose lines answering 200 ids and `"count": 201`;
   the request the message names answering `200` (a flagged line on the open last day letting the
   close through is proven in tests/contract/test_sealed_periods.py); the previous statement's last day sealed once it is completed.
5. **A fix checks the close at once** (question 12; waits on the engine ask "A close can be
   checked before it is sent"): on the screen from `c`, a save from `⏎` sends the close as a dry
   run, as a save on the upload's screen sends the paper.

## Reply to the engine

Part 3 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"): part A, 1 to 3. It reports on the hand-off's "Done when" checks for a refused close
or upload showing the loose lines and no screen cleaning up after the close, and any contract
problem found, and names the ask "A loose-lines refusal names its lines by id, in a field a client
reads" as what it was built on. It is also part 3 of the reply to the hand-off of 2026-11-11 ("A
loose-lines refusal names its lines by id in `error.details`…"), items 1 and 2, reporting on its
"Done when" checks for a close refused for one loose line, an upload's dry run refused for two
(one taken out of the draft) and a refusal for 201 lines, and closes that ask.

## Found along the way

Not built in this spec; sorted when it is done.

- **The upload preview spills under its footer after a resize from 120 to 80 columns,** and on a
  fresh window narrower than about 80, with the old flagged note as with the new
  (`_budget` in expense/tui/screens/statement_upload.py).
- **`_flagged_head_lines` falls back to the screen's width before the body is laid out,** leaving
  out the body's 4 cells of padding, where `_columns` takes them off; the dry run's answer comes
  after layout, so it has not been seen.
- **The 80-column wrap test's `startswith("  ")` check is true by construction**
  (test_tui_statement_upload.py, `test_a_full_page_with_a_flagged_line_wraps_its_head_and_ends_above_the_footer_at_80x30`);
  it would also take a three-cell indent.
- **docs/mockups/expense-world-moves-and-preview.html still draws the old note** `on the paper's
  days` (:134, :163).
- **`r` pressed while the Edit form's save is still being sent goes out at once**
  (expense/tui/screens/leftover_lines.py:312-315): `saves_pending()` counts only the screen's own
  writes, so the dry run can read the line before the save lands, and the save's own dry run
  (question 9) then does not follow, the preview being on top; `r` again recovers.
- **`test_r_waits_for_a_delete_still_being_sent` reads `app._notifications`**
  (tests/unit/test_tui_leftover_lines.py:369), where docs/tui.md §6 asks for a patched `notify`.
- **Two lines of docs/tui.md's "`d` is the TUI's one destructive key" passage run past the wrap
  width** (about :978-980).
