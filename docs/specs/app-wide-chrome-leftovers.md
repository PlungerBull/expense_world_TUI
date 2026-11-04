# Every screen's frame, as the Statements drawings show it

What part 7 of the currencies catch-up, an account's statement on one screen (done on
2026-11-03), turned up that touches every screen, not only the Statements ones.

**Status: every question answered and the six tasks approved by the owner on
2026-11-03.** It waits on no other spec, and
[the Statements screens as drawn](statements-screens-as-drawn.md) runs after it. When done,
the why moves to [decisions.md](../decisions.md) and this file is deleted.

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
5. **`pgup Prev` only where there is a page before** (What it must do 5): the footer of
   `CursorList` ([cursor_list.py](../../expense/tui/widgets/cursor_list.py)) and the other
   lists that bind it hide the key on the first page.
6. **Incomes carry their `+`** (Decided 4 and 5): every list writes `+` before a positive
   transaction amount, through the shared amount cell
   ([cells.py](../../expense/tui/widgets/cells.py), `AMOUNT_RULE` in
   [theme.py](../../expense/tui/theme.py)); account balances and totals, which share that rule
   today, stay unsigned.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- A code comment and some test docstrings name drawing panes, which is provenance: the
  comment above `FlaggedLinesScreen #fhead` in [app.tcss](../../expense/tui/app.tcss)
  ("pane 10"), and docstrings in `test_tui_flagged_panes.py` and `test_tui_reconciliations.py`
  ("pane N").
- In [test_tui_create_forms.py](../../tests/unit/test_tui_create_forms.py), `_run_refused` and
  its callers still take a `monkeypatch` they no longer use, and
  `test_an_emptied_colour_bar_goes_back_to_the_rows_own_swatch` asks for toasts it never reads.
