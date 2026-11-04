# A long account name in the LOG bar peek's count line

What the reads and writes catch-up's leftovers (done on 2026-11-03) turned up: the account
peek's count line now names the pick, `3 of 48 in VISA Infinite Sapphire · USD · newest first`,
and with a long account name that line no longer fits.

**Status: drafted on 2026-11-03 for the owner to rewrite or approve; one question, with a
mockup to draw before you pick.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

At 80 columns the peek is about 72 letters wide. A pick label over about 40 letters, such as
`1716 of 1716 in <a long account name> · PEN · newest first`, wraps the count line onto a second
line. The peek sizes itself for one count line, so the second line is cut off and the end of
the count, often the currency, is lost.

## What it must do

1. **The count line always reads whole enough** to tell which account and currency it counts,
   as question 1 picks, at 80 columns with a 50-letter account name.

## How the owner knows it is done

1. With a 50-letter account name at 80×24, the peek's count line shows as question 1 picks and
   nothing under it is cut off.
2. The unit suite passes.

## Questions for the owner

### 1. A count line too long for the peek? (mockup to draw)
- **A.** The account name gives way with `…`, keeping the count, the currency and
  `newest first`.
- **B.** The count line takes a second line, and the peek shows one row fewer.

**Recommended:** A, because the title just above the count already names the account in full.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
