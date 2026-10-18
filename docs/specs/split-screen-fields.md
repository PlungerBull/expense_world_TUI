# The split screen: a table of the parts, each part's fields below

**Status: approved 2026-10-18.** The screen is the owner's
design, approved 2026-10-18 in
[expense-world-split-screen.html](../mockups/expense-world-split-screen.html). When done, the
why moves to [decisions.md](../decisions.md), and this file is deleted.

---

## What it must do

**Splitting a transaction is done with fields, not a typed line.** `s` on a ledger row opens the
split screen, as today; what changes is how the parts are typed.

- **On top, a table of the parts.** One row per part: amount, category, hashtags, note. Above
  it, the transaction's title; under it, `+ add a part` and the line adding the parts up against
  the transaction's total. The cursor moves through the title, the parts and `+ add a part`.
- **`⏎` on a part opens its fields below,** one per line, as on the Edit form: amount,
  category, hashtags, note, with the Edit form's suggestion list on the category and hashtags.
  Each field left shows in the table at once. `⏎` on the last field goes back to the table.
  `esc` goes back to the table too, keeping every field already left; only the field being
  typed goes back to what it was.
- **`⏎` on `+ add a part`** adds an empty part and opens its fields, the cursor on its amount.
  A part left with nothing typed drops again.
- **`⏎` on the title** opens one field below. A new title changes the title on every part, and
  is sent with the split in one write. This needs the engine to take a title with the split.
- **`esc` on the table leaves at once,** nothing sent. `^x` drops the part under the cursor.
  `^s` sends the split, as today.
- **Opening a transaction already split** shows its parts in the table, ready to change, drop
  or add to.

## How the owner knows it is done

1. `s` on `Tottus Jockey Plaza -100.00` opens the table. Adding two parts, -60.00 COMIDA #casa
   and -40.00 HOGAR, and pressing `^s` leaves two rows of Tottus in the ledger.
2. Typing `ho` in a part's category shows HOGAR and HOSPEDAJE to pick from.
3. `esc` on the table goes back to the ledger, with Tottus still one row.
4. Changing the title to `Tottus — semana` before `^s` leaves both parts titled that way.
5. `s` on either part of a split transaction opens the table with both parts.
6. Parts that make -90.00 of -100.00 show `-10.00 left` in red; `^s` shows the engine's refusal
   under the parts and splits nothing.

## Tasks

Approved 2026-10-18. Both tasks are done: task 2, the title sent with the split, was built as
task 1 of [split-title-and-reconciliation-read.md](split-title-and-reconciliation-read.md). The
acceptance check runs next.
