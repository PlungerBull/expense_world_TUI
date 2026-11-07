# Small fixes on screen

Seven small things you see in the app, found while other specs ran, gathered into one spec so
they are answered in one round and built in one run. Each was its own spec or Backlog item
until 2026-11-06.

**Status: every question answered and the mockups picked on 2026-11-07; the tasks are drafted
for the owner to approve.** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and
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

Each point above, as "Decided" below picks; point 5 is parked.

## How the owner knows it is done

1. At 80×24, the LOG bar's legend shows as picked; with a 70-letter account name picked, the
   peek's title shows as picked and its count line is not cut off.
2. At 140×24 and at 80×24, the ledger's `?` card shows `s Edit` and `d Delete`, as picked.
3. The "no statement" `?` card lists the keys as picked, and fits a 24-row terminal.
4. (Point 5 is parked; nothing to check.)
5. A Manage form left while it saves, answered by a server error, while its list shows: the
   list does as picked.
6. The Edit form opened on a deposit from the "no statement" list writes its heading as picked.
7. The unit suite passes.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | The LOG bar's legend at 80 columns, in [expense-world-small-fixes.html](../mockups/expense-world-small-fixes.html)? | B1: the legend is the grammar alone, on one line at every width; `⏎ Stage` shows in the footer, `esc Cancel  ⏎ Stage  ^s Save` (2026-11-07). |
| 2 | A peek title too long for the panel, in [expense-world-small-fixes.html](../mockups/expense-world-small-fixes.html)? | A: the account name gives way with `…`, as on the count line; the currency stays (2026-11-07). |
| 3 | A `?` card taller than the screen, in [expense-world-small-fixes.html](../mockups/expense-world-small-fixes.html)? | B: on a wide terminal the card spreads out, its groups side by side, so it shows whole; where it still does not fit (80×24) it scrolls, a dim line saying how much is above or below (2026-11-07). |
| 4 | Which keys the "no statement" `?` card lists, in [expense-world-no-statement-keys.html](../mockups/expense-world-no-statement-keys.html)? | A: only the keys that work there (2026-11-07). |
| 5 | What gives way on a narrow "no statement" list? | D: parked, since the app is built for 80 columns ([todo.md](../todo.md) "Parked") (2026-11-07). |
| 6 | A Manage list after a save that failed with a server error or no answer? | A: the list reads again from its first page, as after a save that landed (2026-11-07). |
| 7 | Does the "no statement" Edit form's heading write a deposit with its `+`, in [expense-world-small-fixes.html](../mockups/expense-world-small-fixes.html)? | A: `Liquidación  ·  +800.00 PEN` (2026-11-07). |

---

## Tasks

Drafted on 2026-11-07, for the owner to approve. Each task lands with its tests and the lines of
[tui.md](../tui.md) that describe what it changes.

1. **The LOG bar's legend fits one line.** The legend under the bar is the grammar alone, with
   no `↵ stages the line`; the footer reads `esc Cancel  ⏎ Stage  ^s Save`, at every width, and
   `⏎` still stages the line (Decided 1, the mockup's B1).
2. **A long account name gives way in the peek's title.** The title is one line at any width:
   the name is cut with `…` so the currency stays whole, as the count line under it already does
   (Decided 2, the mockup's A).
3. **The `?` card scrolls when it is taller than the screen.** On every screen, a card that does
   not fit shows what fits, a dim last line `▼ N more lines · ↓ scrolls`, and `↓` `↑` scroll it;
   scrolled down, a dim first line `▲ N lines above · ↑ scrolls` (Decided 3, the mockup's A
   panes, which B keeps for a narrow terminal).
4. **On a wide terminal the `?` card spreads out.** Where the terminal has room, the card grows
   wider and sets its groups side by side, three across, each key's words on one line, so the
   ledger's card shows whole at 140×24 (Decided 3, the mockup's B at 140×24).
5. **The "no statement" `?` card lists only the keys that work there.** `esc Back` once, `d`,
   `r`, `⏎`, `↓`, and `pgdn Load the next 10 rows` only while rows are left to load; no
   `esc Close the panel`, `n`, `u`, `pgup` or `Next page`; it fits a 24-row terminal (Decided 4,
   the keys mockup's A).
6. **A Manage list reads again after a save whose ending is not known.** A category, hashtag or
   account form left while it saves, answered by a server error or no answer, while its list
   shows: the list reads again from its first page, as after a save that landed (Decided 6).
7. **The "no statement" Edit form's heading writes a deposit's `+`.** `Liquidación  ·  +800.00
   PEN`, as the parts table under it writes it (Decided 7, the mockup's A).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
