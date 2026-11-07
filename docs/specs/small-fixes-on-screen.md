# Small fixes on screen

Seven small things you see in the app, found while other specs ran, gathered into one spec so
they are answered in one round and built in one run. Each was its own spec or Backlog item
until 2026-11-06.

**Status: every question answered, the mockups picked and the tasks approved on 2026-11-07.** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and
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

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The `?` card's side gutters show the screen behind it.** With the card open over the ledger,
  the ledger's own rule peeks out as a one-cell `─` on each side of the card's frame (80×24: cols 3
  and 76, row 4; the wide card the same at cols 3 and 136); the mockups draw those gutters blank.
  Something you see.
- **The Statements account list's `?` card lists page keys that do nothing.** With the panel
  closed, the focused account list's card lists `pgdn Load the next 10 rows under these`,
  `pgdn Next page` and `pgup Previous page`; none works there and the footer shows none of them.
  Something you see.
