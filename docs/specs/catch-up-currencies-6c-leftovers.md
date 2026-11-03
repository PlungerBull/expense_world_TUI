# What part 6b's leftovers turned up

What part 6b's leftovers, the LOG bar's staged list giving way and the "no batch" form's
OPERATION note (done on 2026-11-02), turned up while they ran.

**Status: drafted on 2026-11-02 for the owner to rewrite or approve; one question, with a
mockup to draw before the owner picks.** It waits on no other spec. When done, the why moves
to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **The LOG bar's staged list can cut its title to a bare `…` at 80 columns.** When rows are
  wider than the bar, the title and tags give way and the marker, date, amount, currency,
  account and category keep their whole width ([tui.md](../tui.md) "The LOG bar's account is
  one row per account"). With long account and category names those kept columns fill the
  width: the acceptance check on 2026-11-02 staged lines on an account named
  `contract-BCP Signature` with the category `contract-KORAKUEN`, and every title, even a short
  one, read `…`, as did the tags and both headers. A row then says how much and where, but not
  what.

## What it must do

1. **The staged list keeps some of each title readable at 80 columns** as the question picks.

## How the owner knows it is done

1. At 80 columns, with an account and a category of about 20 characters each, every staged
   row shows the start of its title, and the columns the question keeps whole stay whole.
2. The unit suite and the drift check pass.

## Questions for the owner

1. **When the kept columns leave the title no room** (mockup to draw): does the title keep a
   least width — about 10 characters — with the account, then the category, cut next
   (recommended, so each row still says what it was), or does it stay as it is, the title
   giving way to `…` and the other columns whole.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
