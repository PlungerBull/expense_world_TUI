# The Statements screens as drawn

What part 7 of the currencies catch-up, an account's statement on one screen (done on
2026-11-03), turned up on the Statements screens while it ran: places where the app still
differs from the approved drawing
[expense-world-statements-screens.html](../mockups/expense-world-statements-screens.html).

**Status: both questions answered on 2026-11-03; seven tasks drafted for the owner to
approve.** It runs after [every screen's frame](app-wide-chrome-leftovers.md), whose dropped
blank lines around the breadcrumb are what lets `u` read line for line as drawn. When done,
the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Part 7 made the Statements screens work against the engine and fit 80×24. Its checks then found
smaller differences from the approved drawing, which it listed rather than built:

- **The lines in no statement (`u`) are spaced and keyed differently.** The drawing packs the
  columns: the `!` mark first, the date right after it, and the title taking the room left. The
  app spreads the room over every column. Its caption also breaks at a different word, and its
  footer reads `⏎ Edit  pgup Prev  esc Back  r Refresh  ? Keys  d Delete` where the drawing
  reads `esc Back  ⏎ Edit  d Delete  r Refresh  ? Keys`.
- **The rules under the browse's headers run the whole width.** The drawing draws them 60 wide,
  starting under the first letter of the header.
- **`c`'s refusal is a toast.** The drawing shows `Couldn't complete` and the engine's words as
  lines between the head and the balance box. The app shows a toast in the corner, over the
  box, and it fades.
- **A draft's covered currency shows a blank difference** where the drawing shows a dim `—`.
- **The `⚑` line may cost the statement's page line.** It shows after the list is sized, so a
  statement with flagged lines may lose its `rows … · page …` line (not yet seen in the app).
- **`c`'s boxes cut their words below 64 columns** instead of wrapping them.
- **A long account name cuts the browse's balances.** With a name of about 50 letters, the
  Balances column reads `-260.50 P…` and loses the second currency. With six accounts, the
  accounts' `rows 1-5 of 6 · page 1 of 2` line sits right on the statements' caption, with no
  blank line between.
- **On a two-currency New statement form, an unreadable amount's note does not name its
  currency:** `Begin balance: a signed decimal…` reads the same for soles and dollars.
- **The screens still say "batch"** where they mean a statement: `In no batch`, the
  `u No batch` key and `(no transactions in this batch)`.

## What it must do

1. **The lines in no statement read as drawn:** columns packed, the caption breaking as drawn,
   and the drawing's footer order.
2. **The browse's header rules are 60 wide,** as drawn.
3. **`c`'s refusal shows as lines between the head and the box,** as drawn, and stays until
   the next key.
4. **A covered currency with no difference yet shows a dim `—`.**
5. **The `⚑` line never costs a statement its page line.**
6. **`c`'s boxes wrap their words on a narrow terminal** instead of cutting them.
7. **A long account name gives way in the browse,** so every balance shows whole, and a blank
   line separates the accounts' page line from the statements' caption.
8. **An unreadable amount's note names its currency:** `Begin balance USD: a signed decimal…`.
9. **The word for "batch"** is as question 1 picks.

## How the owner knows it is done

1. At 80×24, `u` reads line for line as the drawing's no-statement list, footer included.
2. At 80×24, a refused `c` shows `Couldn't complete` and the engine's words under the head, with
   the box below them, and nothing in the corner.
3. A draft with a currency whose ending balance is not entered shows `—` in its difference.
4. A statement with flagged lines, at 80×24, shows its `⚑` line and its page line together.
5. At 60 columns, `c`'s box shows its whole message, wrapped.
6. With a 50-letter account name, the browse shows both currencies' balances on every row.
7. On a soles-and-dollars New statement form, an unreadable dollar amount's note names USD.
8. No Statements screen says "batch", unless question 1 keeps it.
9. The unit suite, the live suite and the drift check pass.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | "batch" on the Statements screens? | A: "statement": `In no statement`, `u No statement`, `(no transactions in this statement)` (2026-11-03). |
| 2 | Below 24 rows? [expense-world-leftover-picks.html](../mockups/expense-world-leftover-picks.html) pane 2 | A: kept; a terminal too small is the user's to make bigger, and the accounts list keeps its rows (2026-11-03). |

---

## Tasks

Drafted on 2026-11-03 for the owner to approve. Each is checked at 80×24 against
[expense-world-statements-screens.html](../mockups/expense-world-statements-screens.html), in
[reconciliations.py](../../expense/tui/screens/reconciliations.py) unless named.

1. **"statement" for "batch"** (Decided 1): `In no statement`, the `u No statement` key and its
   tooltip, `(no transactions in this statement)`, and every other "batch" a Statements screen
   shows; tests and tui.md follow.
2. **The lines in no statement read as drawn** (What it must do 1): the `!` mark first, the date
   after it, the title taking the room left; the caption breaking where the drawing breaks it;
   the footer `esc Back  ⏎ Edit  d Delete  r Refresh  ? Keys`.
3. **The browse as drawn** (What it must do 2 and 7): the header rules 60 wide under the
   header's first letter; a long account name gives way with `…` so every balance shows whole;
   a blank line between the accounts' page line and the statements' caption.
4. **`c`'s refusal under the head** (What it must do 3): `Couldn't complete` and the engine's
   words as lines between the head and the balance box, no toast, gone at the next key.
5. **`c`'s boxes wrap** (What it must do 6): below 64 columns a box's words wrap instead of
   being cut; tested at 60 columns.
6. **The `⚑` line keeps the page line** (What it must do 5): the list is sized after the `⚑`
   line is counted, so a statement with flagged lines shows both at 80×24.
7. **Two small words** (What it must do 4 and 8): a covered currency with no difference yet
   shows a dim `—`; on a two-currency New statement form an unreadable amount's note names its
   currency (`Begin balance USD: a signed decimal…`).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
