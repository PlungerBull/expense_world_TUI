# The app on contract 1002f105c6bacdf1, and the preview names the lines the close will flag

Catches up to contract `385b112ad7f34bb8` through `1002f105c6bacdf1`, everything in the engine's
hand-off of 2026-11-08 but an account's bank, numbers and built name, which
[accounts-carry-their-numbers.md](accounts-carry-their-numbers.md) takes. The engine's four later
versions (`cd6574eee1dd5ec0` to `a7dd5e3ed5da676f`) go to the next catch-up.

**Status: approved on 2026-11-08, its questions answered on the mockup
[expense-world-moves-and-preview.html](../mockups/expense-world-moves-and-preview.html).** When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine now does five things the app did itself or could not do: it lists the supported
currencies, takes a one-currency account's currency when a write names none, moves a line onto
a one-currency account in another currency, sends each transaction's own calendar day, and
states the largest amount it takes. The app drops its own versions of each.

A statement PDF's preview is where the owner checks an upload before anything is written. A
line the owner logged on a day the paper covers, which the paper does not hold, is often a
typo'd amount or a purchase the bank books next month; today it shows only after the close. The
engine's dry run now names the lines the close will flag.

## What it must do

1. **The currencies come from the engine,** in every list and picker; the app keeps no list.
2. **A one-currency account's currency is the engine's to fill,** on a new transaction and on a
   move. A move into another currency says the amount was not converted.
3. **Each transaction shows on its own day,** the engine's, in every list.
4. **An amount past the largest is refused in the engine's words,** typed or in a file, and no
   screen crashes printing a huge one.
5. **The preview lists the lines the close would flag,** before anything is written, with the
   close's notes for each currency.
6. **The live contract suite runs on the new engine** and proves each of these.

## How the owner knows it is done

1. The currency picker comes from the engine; no PEN/USD list is left in the app.
2. A transaction on a soles-only account is created without choosing a currency; on the Visa the
   app asks for one.
3. A dollar purchase moved by account to a soles-only account shows as the same amount in soles,
   and the app says it was not converted.
4. Removing a currency that is in use shows the refusal naming that currency.
5. Typing `1e5000`, or any amount past the largest, is refused, and no screen crashes; a file
   holding such a row shows the refusal on that row.
6. A transaction logged at 23:30 in Lima shows on its own day in every list, and filtering by
   that day finds it.
7. A PDF whose month holds a ledger line the paper lacks shows that line in the preview as one
   the close will flag, under its currency; a paper with nothing to flag shows none; leaving the
   preview writes nothing. After the close, the same line shows on the `⚑` line, as today.
8. The tester logs a transaction on the practice account `BCP-0000` in the real app, against the
   practice engine, with the id the seed printed.

## What the engine declined, or did differently

- **No number of decimals per currency:** every amount is cents, both currencies have two.
- **A total is never capped:** a balance or a month's figure may pass the largest amount; only
  what is sent in or read from a file is bounded.
- **An activity entry's snapshots carry no `day`:** it would go stale when the time zone
  changes; an entry's day is read from the transaction it names.
- **The practice account is `BCP-0000`,** not `Practice account`: bank accounts' names are built.
- **The preview also carries `warnings` and `coverage_gap`,** and flags a line it takes out when
  the close reviews that line's day.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Show the lines the close will flag in the preview? | A: yes, before you confirm; the engine names them on the dry run (2026-11-05). |
| 2 | A line moved to a soles-only account, mockup pane 1? | A: the Edit form's currency line reads `PEN · was USD · not converted`, and after `b` the note counts the rows whose currency changed, asking nothing (2026-11-08). |
| 3 | The preview's flagged lines, mockup pane 2? | A: a `⚑ Will be flagged` block under the lines taken out, each line under the table's columns, its count beside the others (2026-11-08). |

---

## Tasks

Approved. Each reads the live contract on the practice engine before
building.

6. **The largest amount.** An amount the app cannot read as a plain number (an exponent such as
   `1e5000`) is unreadable before sending; anything else is sent, and `OUT_OF_RANGE` shows in the
   engine's words on its line or file row; no formatter crashes on a huge amount; the Backlog's
   "A huge amount reads, then crashes what prints it" closes.
7. **The preview lists the lines the close will flag,** as question 3 is answered, with each
   currency's `⚠` notes under the balances and the currencies the paper does not cover; the
   lines are read once by their ids, as the lines taken out are.
8. **The live contract tests:** `GET /currencies`; a currency left out, single and batch, and
   `REQUIRED` on a two-currency account; an account-only move into another currency; a currency
   removal's keys; the bound one cent past and
   `1e5000`, typed and in each file; the dry run's notes and `not_covered`; `card-soles-only`
   left untested and named in the reply (no practice account can take it); a zero-amount `SALDO INICIAL` dated before the opening balance (the
   Backlog's item closes).

## Reply to the engine

Part 1 of the reply to the hand-off of 2026-11-08, covering `385b112ad7f34bb8` to
`1002f105c6bacdf1` but sections 12 and 13. It reports on the hand-off's "Done when" checks named
in "How the owner knows it is done" above, any contract problem found, and closes the asks "A
read lists the supported currencies", "Say whether an account can hold no currency, and what a
client does with one", "An account's only currency is taken when a write names none",
"Removing a currency names the currency in every refusal", "Say whether a zero-amount row dated
earlier stops a sheet row being the opening balance", "State the largest amount the engine takes,
and refuse past it everywhere", "Send each transaction's calendar day with it", "A statement PDF's
dry run names the lines the close will flag" and "Give the shared practice user an account that
every reseed keeps". The account form's one write is reported in part 2.

## Found along the way

Not built in this spec; sorted when it is done.

- **No live test can close a soles-only month from a sample.** A sample uploads only to an
  account numbered `…0000`, names are unique, and the practice account `BCP-0000` holds soles and
  dollars, so `card-soles-only` has no account to go to; task 8 says so, and the reply names it as
  a contract problem.
- **The engine moved again,** to `eb3082ec9723ec4f`, past the four later versions; it goes to the
  next catch-up with them.
- **The shape-first test's docstring** in `tests/contract/test_account_create.py` names "a
  person's empty name" though every body there is a bank account.
- **Two small test-helper cleanups:** `test_day_of_reads_the_users_zone_whatever_the_machine_zone_is`
  (tests/unit/test_fake_engine_answers.py) calls `monkeypatch.undo()`, which also lifts the
  autouse guards for the rest of that test; `_CLOSE_NOTES`' lists in tests/unit/helpers.py are one
  object shared by every upload answer, where each call used to make fresh ones.
- **`n` on Manage ▸ Accounts stays on while the list shows "Could not load."** It opens a New
  form whose `currencies` line has nothing to pick, since the currencies come with the list's read;
  typing `PEN` says `No currencies match "PEN".` instead of the engine's words. Whether `n` turns
  off until the list loads is the owner's call.
- **`b`'s note when the moved rows came from several currencies** gives one sentence per currency
  (`2 were USD, now PEN, not converted.` then `1 was EUR, now PEN, not converted.`), which the
  mockup did not draw; it cannot happen while the engine lists only PEN and USD. To confirm with the
  owner when a third currency comes.
- **For decisions.md at the sweep:** the suite marks its bank accounts by a number starting `9`
  (the cleaner's rule), since the engine builds the name; sample uploads go to the seed's
  `BCP-0000` by its id, since a second `…0000` account cannot exist.
