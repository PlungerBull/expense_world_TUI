# Empty lists' `?` cards, and leaving a screen while it draws

Three things the `?` card's leftovers (done on 2026-11-07) found and did not fix: two cards
that list keys doing nothing on an empty list, and a crash when you leave a screen in the
moment it draws its list.

**Status: drafted on 2026-11-07 for the owner to rewrite or approve; no question open; tasks
drafted for the owner to approve.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

1. **An empty ledger's `?` card lists page keys that do nothing.** With no rows ("no filter · 0
   of 0 loaded"), the card lists `pgdn Load the next 10 rows under these`, `pgdn Next page` and
   `pgup Previous page`, at 80 and 140 columns; none works there and the footer shows none.
2. **With no bank accounts, the Statements account list's card lists `⏎ Its statements` and
   `↓ Down (↑ up)`,** with no row for either to act on.
3. **Leaving a screen in the moment it draws its list can crash the app.** Pressing `esc`, or
   quitting, just as the Statements screen puts up a list it has read stops the app with an
   error instead of leaving. It is rare: the window is the instant between the list arriving
   and it being drawn.

A card lists a key only while it works ([decisions.md](../decisions.md) "The `?` card shows
whole and lists only keys that work"), so points 1 and 2 need no question; point 3 changes
nothing you see but the crash.

## What it must do

Each card lists only the keys that work on it as it stands, empty or not; leaving a screen at
any moment leaves it, with no error; nothing else you see changes.

## How the owner knows it is done

1. On an empty ledger, the `?` card lists no `pgdn` or `pgup` row.
2. With no bank accounts, the Statements account list's card lists no `⏎` or `↓` row.
3. The unit suite passes, with a test that leaves the Statements screen while its list is
   being drawn.
4. The drift check and the live contract suite pass against the practice engine.

---

## Tasks

Drafted 2026-11-07, for the owner to approve. Each task's "passes if…" is written when it starts.

1. **Leaving mid-draw** (point 3): a screen's list hand-back checks the screen is still there
   after it waits for the list to draw, in one shared place
   ([_base.py](../../expense/tui/screens/_base.py) `call_while_attached`), for the Statements
   screen's `_show` and `_open_panel` and any `_show` with work after its wait.
2. **The empty lists' cards** (points 1 and 2): the ledger's page keys and the account list's
   `⏎` and `↓` listed only while they work.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
