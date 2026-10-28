# The app reads and writes on the engine's new routes

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`);
then to `e7393dd869963db1`: the holder part of the engine's hand-off of 2026-10-28, "A person
carries an opening balance, and a card is now called a holder everywhere" (`2cec1b59048f50dc`
and `e7393dd869963db1`).
This is part 1a of seven specs that share the range of the hand-off of 2026-10-27, run in this
order:

1. this one: the app's reads and writes on the engine's new routes and names, the statement
   PDF upload among them, with nothing you see changing;
2. [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md):
   the statement screens on the engine's new routes, with nothing you see changing;
3. [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md):
   the live tests' shared helpers, and a statement's life, on holders;
4. [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md):
   the live tests of the upload on the published sample PDFs, bank lines, holders and people;
5. [catch-up-split-rows.md](catch-up-split-rows.md): the sheet import's counts line;
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md): cards in the
   app;
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md):
   a card's statement on one screen.

**Status: approved by the owner on 2026-10-28; the current spec.** When done, the why moves to [decisions.md](../decisions.md)
and this file is deleted.

**Built on the holder names.** The engine calls a card a holder since contract
`e7393dd869963db1` (its hand-off of 2026-10-28, "A person carries an opening balance, and a card
is now called a holder everywhere"): `/holders`, `holder_id` everywhere, `GET
/statements?holder_id=`, and every reason and message says holder, with nothing behaving
differently (contract: "Holders"). "Card" stays for the bank's product: a credit card, its paper
and its download. This spec uses the holder names, so no request names `/cards` or `card_id`.
People become holders in a later engine change, the one the engine coders named in their answer
of 2026-10-27, "Which of the terminal app's seven card and statement specs the engine's coming
changes touch", so the bank download's account list is built only from holders that are not
people.

---

## Why

On 2026-10-27 the engine made a holder its own thing, holding its accounts, one per currency,
and made a holder's monthly statement one record for the whole holder (contract: "Holders")
(contract: "Statements"). The routes the app called for reconciliations are gone, and several
names the app sends and reads were renamed. The engine on your computer already runs this
version, so today these break:

- moving a transaction to another account, on the Edit form or several at once in the ledger;
- the statement PDF upload, and the bank download's list of accounts;
- the Reconciliations screens (part 1b).

This spec puts the app's reads and writes, and the statement PDF upload, back on the engine's
new routes, **with the screens as they are today**: the same keys, the same words, the same
layout. The Reconciliations screens follow in part 1b; the screens that change for holders and
whole-holder statements come in parts 6 and 7, from mockups you pick.

**Still broken after this spec, until part 6 ("Cards in the app"):** creating a bank account,
`t` turning a person back into a bank account, `a` archiving a bank account, and the sheet
import's `--create-names`. Each needs a holder, and how the app gives an account its holder is
your pick in part 6. Until then, each shows the engine's refusal.

## What it must do

1. **The fake engine the unit tests run against answers as the engine does now**: statements
   and holders on their own routes, and an account carrying its holder (contract: "Holders").
2. **A transaction's statement is named as the engine names it now.** A move to another
   account takes the transaction out of its statement, as today, under the new name
   (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment").
3. **A holder's accounts are found through the holder.** The bank download's and the PDF
   upload's account list pairs a holder's two accounts from the holder, with the line's words as
   today (contract: "Holders").
4. **The statement PDF upload works again on the engine's new route and answer**, with its
   screens as built. A savings PDF sent for a holder that holds another currency is refused in
   the engine's words (contract: POST /v1/statements/import, "Every account of the holder is on the paper").

## How the owner knows it is done

1. Moving a transaction to another account saves, and says it left its reconciliation, as
   today.
2. A statement PDF upload previews and closes its month, as built.
3. The bank download's list of accounts shows a holder's two accounts as one line, as today.
4. The unit suite and the drift check pass, on the version this client last recorded. The
   live suite passes once parts 2a and 2b are done.

## Questions for the owner

None: what you see stays as it is. The two questions about the flagged lines and the app's
line on `t` are in part 1b.

---

## Tasks

Drafted 2026-10-27; approved by the owner on 2026-10-28. Each leaves `pytest tests/unit` green.
Each task fixes the `(contract: …)` citations and the [tui.md](../tui.md) and
[runtime.md](../runtime.md) lines of the code it touches.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`), then `2cec1b59048f50dc` and `e7393dd869963db1`
  (the rename), reaching `e7393dd869963db1`, shared with the six other parts;
  `d34fc8d06ff652c4` and `4ac20e42cf8566ee` are
  answered by the catch-up on a person's opening balance, done on 2026-10-28.
- **The engine's "Done when" checks to report on:** this client's contract snapshot is at
  `e06456a20aca6e4c` (recorded in commit `ab67440`), and it reports having read up to it; and
  "Every holder screen works against /holders with holder_id, and no request names /cards or
  card_id".
- **The asks it closes:** none.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- [clean_practice_user.py](../../scripts/clean_practice_user.py)'s printout reads each account's
  `statement_code` ("no code" otherwise), which an account no longer carries: the code is the
  holder's (contract: "Holders"). Found by task 2.
- [check_fixture_drift.py](../../scripts/check_fixture_drift.py) reads a fixture's keys only
  from quoted `"key":` dict literals, so a key a test passes to a builder as a keyword argument
  (`account_record(statement_partner_id=…)`) is never checked against the contract. Found by
  task 2's review.
- **A question for the owner:** a holder may hold an account in each of three currencies or more
  (contract: "Holders"). The import door's account list names such a holder's line by the rule
  it uses for two: their shared name, or every name joined by ` / `. No such holder exists in the
  owner's data. Found by task 4.
