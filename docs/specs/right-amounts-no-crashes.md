# Right amounts, no crashes, and the picks already made

**Status: approved by the owner on 2026-10-23; the loop runs its tasks.** Drafted by the
orchestrator from the owner's "yes, single spec" that day, over seven todo.md items whose
choices the owner had already made. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Before the official import and daily use, the app must never save a wrong amount, never crash
on a bank file, and never fail a split without saying why. Four smaller items are choices the
owner made on 2026-10-15 and 2026-10-18 that are not built yet.

## What it must do

1. **An amount with a dot before its comma is refused.** `13.853,20` is saved today as 13.85.
   Every amount field (the LOG bar, the Edit form, the split screen, the opening balance)
   refuses an amount whose comma comes after its dot, with the field's usual "can't read that"
   note (owner, 2026-10-15).
2. **A bank file cell reading `nan` or `inf` refuses that row, not the whole file.** It is "not
   an amount", like any other unreadable cell; the rest of the file imports.
3. **A split part holding only #Pendiente drops** when its fields close, as an empty part does,
   so the split is never refused for a part you could not see.
4. **The colour line starts on the row's own colour** on the Edit screens of Manage ▸
   Categories and Accounts, so `⏎` keeps it (owner, 2026-10-15), and stepping past it never
   shows the colour as gone. An account with no colour starts on nothing and `⏎` skips it; a
   colour that is not one of the swatches is kept as it is.
5. **Two wordings in Reconciliations ▸ "no batch"** (owner, 2026-10-18): the `?` card's line
   for `⏎` reads "Edit the row: its date, title, operation, amount or account"; `c`'s question
   says "1 ticked row" for one and "5 ticked rows" otherwise.
6. **The note after `b` counts what moved** (owner, 2026-10-18): `b` on one part of a split
   transaction moves every part, so the note reads `2 rows → BCP Oro PEN · 2 left their
   reconciliation`. The count comes from the engine's answer; if the answer does not say what
   moved, this becomes an engine ask, never one read per part.
7. **The sheet import's report reads right**: a category is "category", never "categorie"; and
   one missing name the sheet spells two ways (`NEW`, `new`) shows on one `Not sent:` line.

## How the owner knows it is done

1. Typing `13.853,20` as an amount on the LOG bar or the Edit form is refused with the field's
   note; `13853.20` saves 13,853.20.
2. A bank file with `nan` in one amount cell imports every other row, and that row is listed as
   not an amount.
3. On the split screen, a part left with only #Pendiente disappears from the table.
4. On a green category's Edit screen, `⏎` down every line saves nothing and the category stays
   green.
5. The two "no batch" wordings read as above.
6. `b` on one part of a split transaction says how many rows moved.
7. A sheet import with a category it cannot create says "category".

---

## Tasks

Approved by the owner on 2026-10-23. One task per item above, in order.

Item 6, the note after `b`, waits on the engine: its answer to a move names only the
transaction sent, so the ask
[a-line-move-answers-what-it-moved.md](../to-engine/a-line-move-answers-what-it-moved.md) goes
to the engine, and the item leaves this spec for [todo.md](../todo.md); its check 6 is not part
of this spec's acceptance check.
Every other task is done; the acceptance check follows.
