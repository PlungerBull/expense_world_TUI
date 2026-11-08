# Empty lists' footers, and the other lists' `?` cards

What the empty lists' `?` cards (done on 2026-11-08) found and did not fix: on an empty list, the
footer still names keys with no row to act on, and so do the `?` cards of Manage's three lists
and one line of the ledger's card.

**Status: drafted 2026-11-08 for the owner's approval; its mockup is drawn with it, at the next
summary.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

1. **On an empty ledger the footer still shows `⏎ Open` and `space Select`,** and on the empty
   Statements account list `⏎ Its statements`; none works there.
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

1. On an empty ledger the footer shows no `⏎ Open` or `space Select`, and the card's `esc` row
   reads only "Go back".
2. On the empty Statements account list the footer shows no `⏎ Its statements`.
3. On an empty Accounts, Categories or Hashtags list, the `?` card lists no key that needs a row.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Does the footer leave out a key with no row to act on, as the card does? | Waiting; asked with the mockup. |

---

## Tasks

Drafted with the mockup.

## Found along the way

Not built in this spec; sorted when it is done.
