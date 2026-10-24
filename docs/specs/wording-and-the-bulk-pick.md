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
