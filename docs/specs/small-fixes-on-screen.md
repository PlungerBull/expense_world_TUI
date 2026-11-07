# Small fixes on screen

Seven small things you see in the app, found while other specs ran, gathered into one spec so
they are answered in one round and built in one run. Each was its own spec or Backlog item
until 2026-11-06.

**Status: drafted on 2026-11-06; seven questions open, each drawn where it shows on screen; for
the owner to answer and approve.** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and
this file is deleted.

---

## Why

1. **The LOG bar's legend at 80 columns.** The line under the LOG bar, `$account · %currency ·
   @category · #tag · ±amount · //note · when` then `↵ stages the line`, is wider than an
   80-column terminal, so `stages the line` drops to a second line. The legend is meant to be
   one line, and the extra line is a row the account peek no longer has.
2. **The LOG bar peek's title with a very long account name.** The peek's first line names the
   account and currency in full. With a name over about 60 letters it no longer fits the peek's
   72 columns; the second line pushes the count line out of view. The count line already
   shortens a long name with `…`.
3. **The `?` card at 24 rows.** At 140×24 the ledger's `?` card stops at `m Move the selection
   to a currency`: `s Edit` and `d Delete` fall below the screen, and the card does not scroll.
   A footer too narrow for every key leaves keys out and says `?` lists them, so a key can end
   up shown nowhere.
4. **The "no statement" `?` card lists keys that don't apply.** It shows `esc Back` twice,
   `esc Close the panel` (off there), and both `pgdn Load the next 10 rows` and `pgdn Next page`
   once every row is loaded; on a 30-row terminal it clips its last line.
5. **The "no statement" list on a narrow terminal.** Under 68 columns the Statements screen's
   list of lines in no statement cuts the amount, then the currency; under 62 columns its caption
   wraps a lone `·` onto a line of its own (`In no statement · BCP · 4 of 4 loaded · oldest
   first ·`).
6. **A Manage list after a save whose ending is not known.** You leave a Manage form (a
   category, a hashtag, an account) while it saves, and go back to its list. When the save
   lands, the list reads again. When the engine fails with a server error or does not answer,
   the save may still have landed, but the list stays as it was until `r`.
7. **The "no statement" Edit form's heading and a deposit's `+`.** That form's heading writes
   the line's total as `Liquidación  ·  800.00 PEN`, while the parts table under it and every
   list write the same deposit as `+800.00` ([decisions.md](../decisions.md) "Every screen's
   frame: no blank lines at the crumb, refusals under the form, `+` on incomes").

## What it must do

Each point above, as its question below picks.

## How the owner knows it is done

1. At 80×24, the LOG bar's legend shows as picked; with a 70-letter account name picked, the
   peek's title shows as picked and its count line is not cut off.
2. At 140×24 and at 80×24, the ledger's `?` card shows `s Edit` and `d Delete`, as picked.
3. The "no statement" `?` card lists the keys as picked, and fits a 24-row terminal.
4. The "no statement" list at 60 columns shows its amount and currency as picked, and its
   caption leaves no lone `·` on a line.
5. A Manage form left while it saves, answered by a server error, while its list shows: the
   list does as picked.
6. The Edit form opened on a deposit from the "no statement" list writes its heading as picked.
7. The unit suite passes.

## Questions for the owner

1. **The LOG bar's legend at 80 columns?** Pick in [the mockup](../mockups/expense-world-small-fixes.html):
   - **A.** Leave it on two lines; nothing is cut.
   - **B1.** One line: `⏎ Stage` moves to the footer beside `esc` and `^s`.
   - **B2.** One line: `↵ stages the line` is left off when it does not fit beside the legend.
   - **B3.** One line: single spaces between the legend's tokens, so both fit.
   **Recommended:** B1. The legend is meant to be one line, the peek gets its row back, and a
   key sits in the footer as on every other screen.
2. **A peek title too long for the panel?** Pick in [the mockup](../mockups/expense-world-small-fixes.html):
   - **A.** The account name gives way with `…`, as on the count line; the currency stays.
   - **B.** The title takes a second line, and the peek shows one ledger row fewer.
   **Recommended:** A. It matches the count line under it, and a name that long is rare.
3. **A `?` card taller than the screen?** Pick in [the mockup](../mockups/expense-world-small-fixes.html):
   - **A.** The card scrolls, at every size; a dim last line says how much is below.
   - **B.** On a wide terminal the card spreads out, its groups side by side, so it shows whole;
     where it still does not fit (80×24), it scrolls as in A.
   **Recommended:** B. At 140 columns every key shows at once; only a small terminal scrolls.
4. **Which keys the "no statement" `?` card lists?** Pick in
   [the mockup](../mockups/expense-world-no-statement-keys.html):
   - **A.** Only the keys that work there.
   - **B.** Every key of that list, the ones off right now dimmed.
   **Recommended:** A. Every row does what it says, and the card fits a 24-row terminal.
5. **What gives way on a narrow "no statement" list?** Pick in
   [the mockup](../mockups/expense-world-no-statement-narrow.html):
   - **A.** The operation number goes; the title keeps its room.
   - **B.** The title shrinks further; every column stays.
   - **C.** The title shrinks to 16 letters, then the operation number goes.
   - **D.** Park it: terminals under 68 columns are rare, and the app is built for 80.
   **Recommended:** D. It saves a mockup round and a task for a width you do not use; if not
   D, then C, which keeps the amount and currency whole down to 60 columns. The caption's wrap
   is drawn on the same mockup.
6. **A Manage list after a save that failed with a server error or no answer?**
   - **A.** The list reads again from its first page, as after a save that landed.
   - **B.** As today: the list stays as it was until `r`.
   **Recommended:** A. You see at once whether the change landed, without having to know to
   press `r`. Nothing new is drawn.
7. **Does the "no statement" Edit form's heading write a deposit with its `+`?** Pick in
   [the mockup](../mockups/expense-world-small-fixes.html):
   - **A.** Yes, `Liquidación  ·  +800.00 PEN`, as the parts under it and every list write it.
   - **B.** No, `800.00`: the heading stays as it is.
   **Recommended:** A. A transaction's positive amount is written with its `+` wherever it is
   named.

---

## Tasks

Drafted once the questions are answered and the mockups picked.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
