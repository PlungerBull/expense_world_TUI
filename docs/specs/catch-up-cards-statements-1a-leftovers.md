# What the app's reads and writes on holders turned up

Three small things part 1a of the cards and statements catch-up turned up: the app's reads and
writes on the engine's holders, done on 2026-10-28 at contract `f00534abdde7fa82`.

**Status: draft, for the owner to rewrite or approve; question 1 is answered (B); the spec waits on the owner's approval.** Its tasks
are drafted when the owner approves it. It runs after
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md),
which removes the old reconciliation fixtures the drift check still names. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **A holder may hold three currencies or more.** The engine allows one account per currency on
  a holder, with no limit of two (contract: "Holders"). The import door's account list makes a
  holder's accounts one line, and names it by the rule it uses for a card: the name its accounts
  share once each drops its currency code, or their names joined by ` / `. With three accounts
  named apart, the line reads `Sueldo / Viajes / Euros`. No such holder is in your data today.
- **The practice-user cleaning script prints a statement code no account carries.** It reads
  each account's `statement_code` to print it, or `no code`; the code is now the holder's
  (contract: "Holders"), so it always prints `no code`.
- **The drift check misses some test keys.** It reads a fixture's keys only when written as a
  quoted `"key":`, so a key a test passes to a builder by name (`statement_partner_id=…`) is
  never checked against the contract. An old field can hide there.

## What it must do

1. **A holder's line on the import door's account list is named as question 1 decides.** A
   card's line whose accounts share a name stays as it is.
2. **The cleaning script prints each holder's statement code**, read from the holder.
3. **The drift check reads a key a test passes to an answer builder by name**, and names it when
   the contract lacks it.

## How the owner knows it is done

1. On the import door, a holder of three accounts named apart shows as question 1 picks.
2. The cleaning script's printout shows the practice user's holder codes.
3. The drift check names a made-up field passed to a builder by name, in a unit test.
4. The unit suite and the drift check pass.

## Questions for the owner

1. **The name of a holder's line when its accounts share no name** (drawn in
   [expense-world-holder-pick-line.html](../mockups/expense-world-holder-pick-line.html)).
   - **A.** The accounts' names joined by ` / `, as a card's line is named today.
   - **B.** The holder's own name, read from the engine's holders.

   **Recommended:** A: it needs no second read, and part 6, "Cards in the app", decides how
   holders are named and shown across the app; B can follow from there.

   **Answered 2026-10-28:** B, the holder's own name.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
