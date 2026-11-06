# The LOG bar at 80 columns: the legend and a very long account name

What [a long account name in the LOG bar peek's count line](../decisions.md) (done on
2026-11-06) turned up: at 80 columns two more LOG bar lines take a second line.

**Status: drafted on 2026-11-06; questions 1 and 2 open; for the owner to approve.** It waits
on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

- **The legend.** The line under the LOG bar, `$account · %currency · @category · #tag ·
  ±amount · //note · when` then `↵ stages the line`, is wider than an 80-column terminal, so
  `stages the line` drops to a second line. Nothing is cut off, but the legend is meant to be
  one line that never changes, and the extra line is a row the account peek no longer has.
- **The peek's title.** The peek's first line names the picked account and its currency in
  full, e.g. `Interbank Cuenta Sueldo Mancomunada Familia Quispe · PEN`. With an account name
  over about 60 letters it no longer fits the peek's 72 columns. The peek keeps room for one
  title line, so the second line pushes its last line, the count, out of view. The count line
  already shortens a long name with `…`.

## What it must do

1. **The legend reads as question 1 picks** at 80 columns.
2. **The peek's title and count line both show whole** at 80 columns with a 70-letter account
   name, as question 2 picks.

## How the owner knows it is done

1. At 80×24, the LOG bar's legend shows as question 1 picks.
2. At 80×24 with a 70-letter account name picked, the peek's title shows as question 2 picks
   and its count line is not cut off.
3. The unit suite passes.

## Questions for the owner

1. **The legend at 80 columns?**
   - **A.** Leave it on two lines; nothing is cut.
   - **B.** Make it fit one line; a mockup of the ways to do it is drawn for you to pick from
     before anything is built.
   **Recommended:** B. The legend is meant to be one line, and the peek gets its row back.
2. **A peek title too long for the panel?**
   - **A.** The account name gives way with `…`, as on the count line; the currency stays.
   - **B.** The title takes a second line, and the peek shows one ledger row fewer.
   **Recommended:** A. It matches the count line under it, and a name that long is rare.

Each picked look is drawn as a mockup in [mockups/](../mockups/) before it is built.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
