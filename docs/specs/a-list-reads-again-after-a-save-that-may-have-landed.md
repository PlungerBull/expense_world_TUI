# A list reads again after a save that may have landed

What [a save whose ending is not known](../decisions.md) (done on 2026-11-06) turned up: a
Manage list does not read again after a save that may have landed.

**Status: drafted on 2026-11-06; one question open; for the owner to approve.** It waits on no
other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

You leave a Manage form (a category, a hashtag, an account) while it saves, and go back to its
list. When the save lands, the list reads again from its first page. When the engine fails with
a server error, or does not answer, the save may still have landed, but the list stays as it
was until you press `r`: it may show the old name, or miss the new row.

## What it must do

1. **After a save whose ending is not known, the list does what the question picks.**

## How the owner knows it is done

1. A Manage form left while it saves, answered by a server error, while its list is showing:
   the list does what the question picks.
2. The unit suite passes.

## Question for the owner

1. **A save that failed with a server error or no answer, after you left its form, while its
   list shows?**
   - **A.** The list reads again from its first page, as after a save that landed, so it shows
     whatever the engine now holds.
   - **B.** As today: the list stays as it was until `r`.
   **Recommended:** A: you see at once whether the change landed, without having to know to
   press `r`.

Nothing new is drawn: the list reads again as it does after any save.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
