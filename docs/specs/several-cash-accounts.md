# Several cash accounts

Part of the catch-up to contract `3a4ff8dac458cf83` (the engine's hand-off of 2026-11-11, items
7 and 15): the screens for a user holding several cash accounts. It runs after
[catch-up-to-3a4ff8dac458cf83.md](catch-up-to-3a4ff8dac458cf83.md), whose live tests prove the
engine side.

**Status: approved on 2026-11-11, its questions answered on the mockup
[expense-world-several-cash-accounts.html](../mockups/expense-world-several-cash-accounts.html).**
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine no longer holds one cash account per user named `Efectivo`. A user may make as many
as they like (a wallet, a jar at home, cash kept abroad); the engine names each `CASH-0001`,
`CASH-0002`, … and an empty one can be deleted. The owner's `Efectivo` is already `CASH-0001`.
The app still offers cash only while none exists, names the new one `Efectivo` on its form, and
keeps `d` off a cash row.

## What it must do

1. **The New form always offers `cash`,** and never shows a name the engine has not given.
2. **A cash account with no transactions can be deleted** from Manage ▸ Accounts, after the
   usual question; one holding any is refused in the engine's words.
3. **Each cash account shows on Home** in the accounts' order, by the name the engine gave it.
4. **The LOG bar's `$` finds a cash account like any account,** by its name.

## How the owner knows it is done

1. Making three cash accounts on the practice user shows `CASH-0001`, `CASH-0002` and
   `CASH-0003` (or the next numbers the engine gives), each on Home and on Manage ▸ Accounts.
2. `d` on an empty one deletes it after the question; on one holding a transaction it shows the
   engine's refusal and nothing changes.
3. No screen names a cash account `Efectivo`, and a person named `Efectivo` can be made.
4. `$cash-0002` on the LOG bar lands the line on `CASH-0002`.

## What the engine declined, or did differently

- **A number is never reused:** a deleted `CASH-0002` leaves the next one `CASH-0004`, not
  `CASH-0002`, and a number another account's name already holds is skipped.
- **A cash account's name never changes,** and the client sends none.
- **Past `CASH-9999`** a create is refused `LIMIT_REACHED` (`CASH_NUMBERS_EXHAUSTED`).

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | The New form's name line for cash? Mockup pane 1. | A: dropped, as for a bank account (2026-11-11). |
| 2 | The `cash` mark on Home? Mockup pane 2. | B: dropped; the name says cash (2026-11-11). |
| — | Delete on a cash row, and `$` on the LOG bar? Panes 3 and 4. | As drawn (2026-11-11). |

---

## Tasks

Approved 2026-11-11 on the answers 1A and 2B. Each reads the live contract on the
practice engine before building.

1. **`cash` on the New form, always** (question 1): the type line offers `cash` whatever the
   user holds (`cash_offered` and the `holds_cash` count in expense/tui/screens/accounts.py go);
   with `cash` picked the name line leaves the form, as for a bank account; `CASH_NAME` goes, and
   a cash create left before the engine answers reads as a bank account's does. A
   `LIMIT_REACHED` on `kind` (`CASH_NUMBERS_EXHAUSTED`) shows in the engine's words on the type
   line.
2. **Delete on a cash row** (pane 3): `d` on a cash account's row asks and deletes as on any
   account's row (the `_on_cash` guards on `delete` in expense/tui/screens/accounts.py go), and
   the `?` card lists it; `HAS_TRANSACTIONS` shows the shared way.
3. **Home** (question 2): each cash account in `/dashboard`'s order under its engine name,
   with no mark after it (`CASH_MARK` in expense/tui/screens/home.py goes). A unit test with two
   cash accounts.
4. **No `Efectivo` left:** the comments, docstrings and unit fakes that name a cash account
   `Efectivo` (expense/tui/screens/create_forms.py, the `account_line` docstring in
   expense/tui/screens/accounts.py, the tests listed by `grep -rl Efectivo tests/unit`) use
   `CASH-0001`; the unit tests proving `CASH_EXISTS` and a cash row with no `d` go.

## Reply to the engine

Part 2 of the reply to the hand-off of 2026-11-11 ("A loose-lines refusal names its lines by id
in `error.details`…"): items 7 and 15. It reports on the hand-off's "Done when" check that three
cash creates show `CASH-0001`, `CASH-0002`, `CASH-0003` and an empty one deletes, and any
contract problem found.

## Found along the way

Not built in this spec; sorted when it is done.
