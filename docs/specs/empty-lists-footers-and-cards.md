# Empty lists' footers, and the other lists' `?` cards

What the empty lists' `?` cards (done on 2026-11-08) found and did not fix: on an empty list, the
footer still names keys with no row to act on, and so do the `?` cards of Manage's three lists
and one line of the ledger's card.

**Status: approved on 2026-11-08, its question answered on the mockup
[expense-world-empty-list-footers.html](../mockups/expense-world-empty-list-footers.html).** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

1. **On an empty ledger the footer still shows `⏎ Open` and `space Select`,** on the empty
   Statements account list `⏎ Its statements`, and on an empty Accounts, Categories or Hashtags
   list `⏎ Open` and, greyed, the keys that act on a row; none works there.
2. **On an empty Accounts, Categories or Hashtags list the `?` card still lists `↓`, the page keys,
   and `e`, `c`, `x`, `a`, `t` and `d`,** none of which has a row to act on.
3. **On an empty ledger the card's `esc` row reads "Clear the selection, else go back",** with no
   selection possible.

A card lists a key only while it works ([decisions.md](../decisions.md) "The `?` card shows whole
and lists only keys that work"); whether the footer follows the same rule is the question here.

## What it must do

Each footer and card names only the keys that work on its list as it stands, empty or not;
nothing else you see changes.

## How the owner knows it is done

1. On an empty ledger the card's `esc` row reads `Back`, as on the other lists.
2. On an empty Accounts, Categories or Hashtags list, the `?` card lists no key that needs a row,
   the moving keys included.
3. On every empty list the footer shows the keys question 1 picks.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Does the footer leave out a key with no row to act on, as the card does? | A: only the keys that work; each comes back with the first row (2026-11-08). |

---

## Tasks

Approved.

1. **The empty lists' footers** show only the keys that work: no `⏎ Open` or `space Select` on
   the empty ledger, no `⏎ Its statements` on the empty Statements account list, and no `⏎ Open`
   or row keys, greyed or not, on an empty Accounts, Categories or Hashtags list; each comes back
   with the first row.

All done.

## Found along the way

Not built in this spec; sorted when it is done.

- **The empty statements panel keeps `⏎ Open` in its footer** (`_PanelList`,
  `expense/tui/screens/statements.py`), a key with no row to act on there.
- **A Manage list's row keys leave its footer while it loads,** where they showed greyed; the
  same rule, since none works before the rows land.
- **A screen's row keys are declared twice:** its `CARD_NEEDS_A_ROW` feeds the card, its own
  `check_action` tuples the footer (`expense/tui/screens/_base.py`, `accounts.py`, the ledger
  alike); they agree today. It joins the Backlog's "The `?` card's row rule reads a little
  unevenly in code".
- **After a reload that fails, a Manage card still lists its row keys** from the records read
  before, while the footer drops them (`_by_id` is set only in `build`).
