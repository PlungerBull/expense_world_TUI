# Small screen details

**Status: approved 2026-11-13 as v1.1.** Its answers were picked on 2026-11-13 on panes 1–16
of [expense-world-open-questions.html](../mockups/expense-world-open-questions.html); the panes
picked as built change nothing. When done, the why moves to [decisions.md](../decisions.md) and
this file is deleted.

---

## Why

Small details found while earlier work was built, each drawn as built (A) beside the smallest
change that answers it (B). Six were picked B; one of them needs the engine.

## What it must do

1. **`n` on Manage ▸ Accounts waits for the list** (pane 1 B): while the list shows
   "Could not load.", `n New` leaves the footer and does nothing; it comes back once the list is
   on screen, so a New form always holds what the engine says now.
2. **Every `⚠` note leads with its currency** (pane 3 B): the close screen's notes read
   `⚠ USD: …`, as the upload's preview does, including a note shown as a message after leaving
   the screen.
3. **A statement PDF goes straight to its preview** (pane 8 B): the engine names the account
   from the card number the paper prints, and "Which account is this statement?" goes; a paper
   it can't name an account for shows the engine's refusal.
4. **Home's ACCOUNTS block says `none` when there are no accounts** (pane 11 B), in the same
   word and place as PEOPLE.
5. **`⏎ Open` leaves the Manage lists' footers** (pane 12 B), Accounts and Categories, where
   `⏎` does nothing; Accounts gains room for `a Archive`. Hashtags keeps its footer.
6. **Home follows the number format as soon as it is known** (pane 16 B): right after Setup on
   a new device, and when a pick saved on Auth & profile lands after you've gone back to Home,
   every amount on screen redraws in the pick; nothing else moves.

## How the owner knows it is done

1. Each of the six reads on screen as its pane's B draws it, against the practice engine.
2. `pytest tests/unit`, the live contract suite and the drift script pass.

---

## Tasks

Each task leaves `pytest tests/unit` green.

1. **`n` waits for the Accounts list** (1).
2. **The close screen's `⚠` notes lead with their currency** (2).
3. **Home's ACCOUNTS says `none`** (4).
4. **`⏎ Open` leaves the Accounts and Categories footers** (5).
5. **Home redraws in the number format once it is known** (6), after Setup and after a late save.
6. **The upload goes straight to its preview** (3); waits on the engine ask "A statement PDF's
   upload names its account from the card number the paper prints".

## Found along the way

Not built in this spec; sorted when it is done.
