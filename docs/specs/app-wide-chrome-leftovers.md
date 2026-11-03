# Every screen's frame, as the Statements drawings show it

What part 7 of the currencies catch-up, an account's statement on one screen (done on
2026-11-03), turned up that touches every screen, not only the Statements ones.

**Status: drafted on 2026-11-03 for the owner to rewrite or approve; four questions, two with a
mockup to draw.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Comparing the Statements screens with their approved drawing
([expense-world-statements-screens.html](../mockups/expense-world-statements-screens.html))
showed differences that come from what every screen shares:

- **A form's refusal is a toast.** The New statement form's drawing shows `▌ Failed …` under
  the form, where it stays. Every form in the app shows a refusal as a toast in the corner,
  which fades after a few seconds.
- **`^s` leaves out a value still in the bar.** The New statement form's drawing shows a
  balance typed in the bar, then sent by `^s`. Every form sends only the lines already entered
  with `⏎`, so the engine then refuses the save for the missing value.
- **Every screen spends two blank lines around the breadcrumb.** No drawing has them, so the
  lists show fewer rows than drawn: the lines in no statement fit four where the drawing fits
  six.
- **A long account name cuts the breadcrumb bare.** With a name of about 50 letters, the crumb
  stops mid-word with no `…`, and the `!` rate alert after it is lost.
- **`pgup Prev` shows on a list's first page,** where it does nothing, on every list longer
  than one page.
- **Incomes are written without a `+`.** The statement drawings show `+800.00`, but every list
  in the app writes an income unsigned and an expense with its `-`.

## What it must do

1. **A form's refusal shows as question 1 picks.**
2. **`^s` sends what is in the bar** as question 2 picks.
3. **The blank lines around the breadcrumb** are as question 3 picks.
4. **A long breadcrumb gives way with `…`,** and the `!` rate alert always shows.
5. **`pgup Prev` shows only where there is a page before.**
6. **Incomes read as question 4 picks.**

## How the owner knows it is done

1. A refused save on any form shows as question 1 picks.
2. On any form, a value typed and then sent with `^s` without `⏎` is saved, if question 2
   picks so.
3. At 80×24, every screen spends its top lines as question 3 picks.
4. With a 50-letter account name, the crumb ends in `…` and the `!` shows when a rate is
   missing.
5. No list's first page offers `pgup Prev`.
6. Every list writes incomes as question 4 picks.
7. The unit suite, the live suite and the drift check pass.

## Questions for the owner

1. **A form's refusal** (mockup to draw: today's toast and the block under the form):
   - **A.** A block under the form, on every form, which stays until the next key.
   - **B.** Keep the toast.

   **Recommended:** A, because a refusal you can still read while you fix the line is the point
   of showing it, and the drawing already shows it so.
2. **`^s` and a value typed but not yet entered:**
   - **A.** Keep it: `⏎` keeps a line, on every form.
   - **B.** `^s` also keeps what is in the bar, on every form, then saves.

   **Recommended:** B, because what you see typed is what you expect saved, and the drawing
   shows it so.
3. **The blank lines around the breadcrumb** (mockup to draw):
   - **A.** Drop them on every screen, so lists show more rows, as drawn.
   - **B.** Keep them.

   **Recommended:** A, because rows are what a 24-row terminal is short of.
4. **Incomes in lists:**
   - **A.** Every list writes an income with its `+`, as the drawings do.
   - **B.** Keep incomes unsigned.

   **Recommended:** A, because the sign is always explicit in this app, and the `+` says so at
   a glance.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
