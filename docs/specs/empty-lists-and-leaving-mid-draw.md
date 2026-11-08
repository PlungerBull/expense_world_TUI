# Empty lists' `?` cards, and leaving a screen while it draws

Three things the `?` card's leftovers (done on 2026-11-07) found and did not fix: two cards
that list keys doing nothing on an empty list, and a crash when you leave a screen in the
moment it draws its list.

**Status: approved on 2026-11-07, tasks and task 2's mockup too; its acceptance check waits on
the owner's answer to [todo.md](../todo.md) "The engine's contract moved to ce7749236717b163".** It waits on no other spec. When done, the why moves to
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

Approved 2026-11-07. Each task's "passes if…" is written when it starts.

3. **The drift check reads the new test's words as fixture keys:** `esc`
   (tests/unit/test_tui_leaving_mid_draw.py:55, `if how == "esc":`) and `statements` (:197,
   `{"accounts": screen._accounts, "statements": None}`); the check passes again with neither
   read as a key. Waits on the owner's answer to the moved contract version.

## Found along the way

Not built in this spec; sorted when it is done.

- On an empty ledger the footer still shows `⏎ Open` and `space Select`, and on the empty
  Statements account list `⏎ Its statements`; none works there.
- No test proves the leave guards in the base list screen's draw and error steps, the guards
  after taking the content lock, or the statement lines' guard after their list mounts; each
  could be forced to always pass and every test would stay green.
- On an empty Accounts, Categories or Hashtags list the `?` card still lists `↓`, the page keys,
  and `e`, `c`, `x`, `a`, `t` and `d`, none of which has a row to act on.
- The ledger's list names `CARD_NEEDS_A_ROW` on its instance where `_AccountList` names it on
  its class; `listed_bindings` reads the owner's private `_rows`; the `_stub_engine` docstring in
  test_tui_help.py says every card drops its list keys on an empty list.
- On an empty ledger the card's `esc` row reads "Clear the selection, else go back", with no
  selection possible.
