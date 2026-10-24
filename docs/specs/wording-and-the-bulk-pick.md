# Notes and hints that say what is true, and the bulk pick as a screen

**Status: drafted by the orchestrator on 2026-10-23 from the owner's picks that day; the owner
approved the tasks on 2026-10-24.** The picks are drawn in
[mockups/expense-world-wording-picks.html](../mockups/expense-world-wording-picks.html)
(questions 2 to 6). When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

Several notes and hints say something the screen doesn't do: "enter to save" on lines where `⏎`
moves on, "type a date" where nothing can be typed, "a number needs a sign" on a number that has
one. A non-date in the Edit form's date crashes the app. The bulk edit words its refused rows in
a style of its own, and its pick is a pop-up though it carries rows.

## What it must do

1. **A non-date on the Edit form's DATE is refused at `⏎`** with "Date: use YYYY-MM-DD.", the
   words the app's other date lines use, and never crashes the app (pick 2 D). The same on the
   bank-line Edit form, which shares the form.
2. **The DATE hint on a line where nothing can change says so**: "read-only · its account is
   archived, so nothing here can change · esc to leave" (pick 3 B).
3. **No hint says "enter to save" where `⏎` moves on**: NAME on Manage ▸ Accounts and Categories,
   the Edit form's TITLE and a new reconciliation's NAME read "free text · enter to go on" (pick
   4a A); the account's COLOR reads "optional · enter keeps it · ↑↓ another swatch" on New and
   Edit (pick 4b A).
4. **The bulk edit's refused rows read as the LOG bar's and the import's do**: one shared
   helper, `<field>: <words>` then `rows 1, 3` (pick 5 A).
5. **The bulk `c`, `b` and `h` pick is a full screen**, the rows it changes listed above the bar
   in the ledger's columns, with the pop-up's keys (pick 6 B).
6. **The LOG bar names an amount it can't read**: `tottus -13.853,20 $BCP` is refused with a
   note naming `-13.853,20`, not "a number needs a sign" (the owner's pick, 2026-10-23).

## How the owner knows it is done

1. Typing `abc` on the Edit form's date and `⏎` says "Date: use YYYY-MM-DD." and the app keeps
   running.
2. On an archived account's line in "no batch", the hint says nothing there can change.
3. No line whose `⏎` moves on says "enter to save".
4. A bulk `b` with two refused rows reads like the LOG bar's refusals.
5. `c` on three selected rows opens a full screen listing them above the categories.
6. `tottus -13.853,20 $BCP PEN` on the LOG bar names `-13.853,20` in its note.

---

## Tasks

Approved by the owner on 2026-10-24. One task per item above, in order.

2. **The DATE hint on a line where nothing can change says so**: "read-only · its account is
   archived, so nothing here can change · esc to leave" (pick 3 B).
3. **No hint says "enter to save" where `⏎` moves on**: NAME on Manage ▸ Accounts and Categories,
   the Edit form's TITLE and a new reconciliation's NAME read "free text · enter to go on" (pick
   4a A); the account's COLOR reads "optional · enter keeps it · ↑↓ another swatch" on New and
   Edit (pick 4b A).
4. **The bulk edit's refused rows read as the LOG bar's and the import's do**: one shared
   helper, `<field>: <words>` then `rows 1, 3` (pick 5 A).
5. **The bulk `c`, `b` and `h` pick is a full screen**, the rows it changes listed above the bar
   in the ledger's columns, with the pop-up's keys (pick 6 B).
6. **The LOG bar names an amount it can't read**: `tottus -13.853,20 $BCP` is refused with a
   note naming `-13.853,20`, not "a number needs a sign" (the owner's pick, 2026-10-23).

## How the owner knows it is done

1. Typing `abc` on the Edit form's date and `⏎` says "Date: use YYYY-MM-DD." and the app keeps
   running.
2. On an archived account's line in "no batch", the hint says nothing there can change.
3. No line whose `⏎` moves on says "enter to save".
4. A bulk `b` with two refused rows reads like the LOG bar's refusals.
5. `c` on three selected rows opens a full screen listing them above the categories.
6. `tottus -13.853,20 $BCP PEN` on the LOG bar names `-13.853,20` in its note.

---

## Tasks

Approved by the owner on 2026-10-24. One task per item above, in order.

1. **Refuse a non-date at `⏎` on the Edit form's DATE.** In
   [edit_form.py](../../expense/tui/screens/edit_form.py), checked with the reader the save uses
   ([dates.py](../../expense/dates.py)), so what it takes stays as loose as today. Passes if: unit
   tests with real key presses show `abc` + `⏎` noting "Date: use YYYY-MM-DD." with the cursor
   staying on DATE, on the Edit form and the bank-line Edit form; `ctrl+s` after it never raises;
   a good date still saves.
2. **The DATE hint on an all-locked line.** Passes if: a unit test on an archived account's "no
   batch" line with title and operation set shows the hint "read-only · its account is archived,
   so nothing here can change · esc to leave"; any line still open keeps its own hint.
3. **The hints say what `⏎` does.** Passes if: unit tests pin "free text · enter to go on" on
   Manage ▸ Accounts NAME, Categories NAME, the Edit form's TITLE and a new reconciliation's NAME,
   and "optional · enter keeps it · ↑↓ another swatch" on the account's COLOR on New and Edit;
   no hint on a line whose `⏎` moves on says "save" (a guard test); [tui.md](../tui.md) matches.
4. **One style for refused rows.** The bulk edit's `group_refusals`
   ([transactions.py](../../expense/tui/screens/transactions.py)) gives way to the shared
   `grouped_refusals` ([formatting.py](../../expense/formatting.py)). Passes if: a unit test of
   `b` on three rows, two refused, shows the shared style; no second grouping helper is left.
5. **The bulk pick as a full screen.** `PickerModal`
   ([modals.py](../../expense/tui/screens/modals.py)) gives way to a pushed screen as pick 6 B
   draws it; the rows above the bar
   show at most 5, the rest as "+ N more" (the owner's pick, 2026-10-24). Passes if: unit tests with real key presses show `c`, `b` and `h` opening it with
   the rows above the bar, filtering as you type, `⏎` picking (and `h`'s multi-pick: `⏎` adds,
   empty `⏎` applies, `⌫` drops the last), `esc` leaving with nothing sent; the writes as today;
   [tui.md](../tui.md) matches.
6. **The LOG bar names an amount it can't read.** In
   [quickadd/](../../expense/quickadd/). Passes if: a unit test with real key presses shows
   `tottus -13.853,20 $BCP PEN` refused with a note naming `-13.853,20`, and a line with no
   signed number still gets today's note.
