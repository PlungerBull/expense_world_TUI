# The app on contract 3a4ff8dac458cf83: an error's details, the engine's new words, and the live suite on several cash accounts

Catches up to contract `ebadad5b9499610c` through `3a4ff8dac458cf83`, everything in the engine's
hand-off "A loose-lines refusal names its lines by id in `error.details`, a user may hold several
cash accounts, every message and promise the contract publishes says exactly what the engine
sends, and an import or upload that waits behind another change is judged on what it finds"
(2026-11-11) but two pieces of screen work: the screens for several cash accounts, which
[several-cash-accounts.md](several-cash-accounts.md) takes, and the leftover-lines screen built
on the refusal's ids, which [closing-with-leftover-lines.md](closing-with-leftover-lines.md)
takes. It runs first: until it lands, the live contract suite fails on the engine.

**Status: approved on 2026-11-11.** It has no open question. The version `3a4ff8dac458cf83`
was recorded in the commit that added it. When done, the
why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live engine already runs `3a4ff8dac458cf83`. Every engine error now carries a fifth key,
`details`, which is where a refused close names its leftover lines. A user may hold several cash
accounts, named `CASH-0001`, `CASH-0002`, …, and one with no transactions can be deleted; the
owner's `Efectivo` is now `CASH-0001`. A few messages changed their words, the soles-only sample
statement prints a new number, and two refusals for writes sent at the same moment now mean
something else. The live contract suite fails on all of these until the app catches up.

## What it must do

1. **Every engine error is read whole,** its `details` included, and shown as before.
2. **Nothing in the app or its tests leans on the engine's words:** each reads the code and the
   reason, never a message's text.
3. **A refused bank download or statement upload shows in the engine's words,** never as
   "another upload is running".
4. **The live contract suite runs green on the new engine** and proves each change it names.

## How the owner knows it is done

1. The tester runs the live contract suite against the practice engine, green, with no test
   waiting on the loose-lines ask.
2. The soles-only sample statement uploads to the practice user's soles-only account and closes.
3. The practice user is left with no cash account a test run made.
4. The version check reads `3a4ff8dac458cf83` with no change left to catch up.

## What the engine declined, or did differently

- **The `POST /auth/pat` taken-id message:** the engine's answer is unchanged; the contract now
  quotes both of its messages as sent.
- **The close's own message link** (`?unassigned_in_period_of=`) still lists the flagged lines on
  open days too; the lines that refuse are the ones `details` names.
- **A sheet import sent at the same moment as `make-person`** still lands either way, on the
  person when judged after the conversion; only the bank download is refused.

---

## Tasks

Approved 2026-11-11. Each reads the live contract on the practice engine before building. The
practice engine is reseeded with the launcher's `--force` before the first live run, since the
test database was rebuilt and its practice keys are new.

## Reply to the engine

Part 1 of the reply to the hand-off of 2026-11-11 ("A loose-lines refusal names its lines by id
in `error.details`…"), covering `ebadad5b9499610c` to `3a4ff8dac458cf83` but the screens for
several cash accounts and the leftover-lines screen (parts 2 and 3, in the two specs named
above). It reports on the hand-off's "Done when" checks for the `card-soles-only` test closing
`BCP-0001`, a `null` `bank_code` on the cash account answering `CASH_TAKES_NO_FIELD`, no code or
test matching an underscore noun or the samples route's `404`, a download refused
`PERSON_TAKES_NO_STATEMENT` showing as for a person, and the client reading `3a4ff8dac458cf83`,
and any contract problem found. It closes the four asks from the catch-up notes the hand-off
answers: "`card-soles-only` cannot be tested", "the bound is written two ways", "`POST
/auth/pat`: the taken-id message differs from the contract" and the cash account's two `null`
problems.

## Found along the way

Not built in this spec; sorted when it is done.

- **Two docstrings in tests/contract/test_sealed_periods.py read a little wider than their
  test:** :165 says a draft is "the only place such a row can be" (a row on a sealed day can also
  sit in the completed statement, where a new currency is `LOCKED`); :14-17 says `currency_code`
  alone is `SEALED_PERIOD` "on each of those sent", though the body also sends `statement_id`.
