# A person carries an opening balance

Catches up to contract `4ac20e42cf8566ee`, from `e06456a20aca6e4c`: the engine's hand-off of
2026-10-27, "A person account carries an opening balance like any account" (`d34fc8d06ff652c4`
and `4ac20e42cf8566ee`). It answers no ask: the owner ruled on 2026-10-27 that refusing an
opening balance on a person was a mistake.

**Status: draft, for the owner to rewrite or approve; question 1 waits on the owner, and so do
its tasks.** It stands apart from the cards and statements catch-up and can run before
[catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md).
Its live checks of `make-person` need accounts on cards, so they are in
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md);
a person's own opening balance is tested live here, through `POST /people`, which still exists.
Its acceptance check runs on its own: the unit suite and the person tests of
[test_opening_balance.py](../../tests/contract/test_opening_balance.py), which need no card. The
orchestrator records `4ac20e42cf8566ee` in the commit acting on the owner's answer. When done,
the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

A person is someone you lend to or borrow from, and the balance on their account is that debt.
When you start tracking someone you already owed, or who already owed you, that starting debt is
an opening balance, as it is on a bank account. Until 2026-10-27 the engine refused one on a
person, so a person could only start at zero, and an account with an opening balance could not
be turned into a person until its opening balance was emptied. The engine now takes a person's
opening balance exactly as a bank account's, keeps it when an account becomes a person, and the
sheet import gives a person the opening balance its first `SALDO INICIAL` row holds.

So the app stops hiding the opening balance on people, and stops telling you to empty it before
`t`.

## What it must do

1. **A person's Edit form offers its opening balance** as a bank account's does, the `opening`
   and `as of` lines after the colour, as question 1 decides. Today the form leaves them off a
   person ([create_forms.py](../../expense/tui/screens/create_forms.py), the account Edit form's
   `_has_opening`).
2. **`t` turns an account with an opening balance into a person, keeping it.** The app's line for
   the refusal the engine no longer sends, `Press e and empty its opening balance first.` for
   `HAS_OPENING_BALANCE` ([errors.py](../../expense/errors.py) and [tui.md](../tui.md), "`t`
   turns an account into a person and back" and the table in "When the engine says no"), goes;
   and so does the handling of `PERSON_ACCOUNT` on the opening-balance route, which no operation
   sends now either (the hand-off: both reasons stay in the vocabulary, sent by nothing): in
   errors.py, tui.md, [test_errors.py](../../tests/unit/test_errors.py) and
   [test_tui_opening_balance.py](../../tests/unit/test_tui_opening_balance.py)'s `PERSON_ACCOUNT`
   case. Its cases on the statement routes and the statement code go with those screens and
   tests, in
   [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md),
   [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md)
   and [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md). The order of
   `make-person`'s remaining refusals is the engine's, proven live in 2b.
3. **Tests prove it:** unit tests for the form and for `t`, and a live test of a person's opening
   balance through `POST /people`: `201` under `@Opening`, and a second one refused
   `409 OPENING_BALANCE_EXISTS` on `account_id`, as on a bank account.
4. **The docs say so:** [tui.md](../tui.md)'s lines above and its "An account's opening
   balance lives on its Edit form", and the clause of [runtime.md](../runtime.md)'s paragraph on
   what the live suite does that describes this spec's own test. Its clauses on people turning
   into accounts and back ("no opening balance", "`HAS_OPENING_BALANCE` (before
   `HAS_RECONCILIATION`)") describe tests that stay 2b's, and change there. The decisions.md entry
   "An account becomes a person, and back, with one key" is the orchestrator's, updated when this
   spec ships, in its own sentence only.
5. **The import plan's part is the official import's:** creating every sheet name as a bank
   account and turning people into people after it, keeping their opening balances, is
   [before-the-official-import.md](before-the-official-import.md)'s "What the engine settled".

## How the owner knows it is done

1. On a person's Edit form you add an opening balance, and the person's balance includes it, as
   question 1 decides.
2. `t` on a bank account with an opening balance makes it a person with the same balance, and
   the opening balance is still there. The app cannot create a bank account until
   [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md), so the tester
   uses a practice-engine account made by the live suite's helpers.
3. The unit suite passes, the live test of a person's opening balance passes, and the version
   check reads `4ac20e42cf8566ee`.

## Questions for the owner

1. **A person's Edit form** (drawn in
   [expense-world-person-opening-balance.html](../mockups/expense-world-person-opening-balance.html)).
   - **A.** It shows `opening` and `as of`, as a bank account's does.
   - **B.** It stays as it is: a person gets an opening balance only from the sheet import, or by
     being turned into a person after it was set.

   **Recommended:** A: the engine takes a person's opening balance like any account's, and a
   person's starting debt is a balance like any other.

---

## Tasks

Drafted on 2026-10-27; they wait on the owner's approval and question 1.

1. **A person's Edit form takes an opening balance (builder).** The account Edit form shows and
   saves `opening` and `as of` on a person as on a bank account, and the statement code line
   stays off ([create_forms.py](../../expense/tui/screens/create_forms.py)); the tests that pin
   today's form, `ELIANA` and the person cases in
   [test_tui_opening_balance.py](../../tests/unit/test_tui_opening_balance.py), follow;
   [tui.md](../tui.md)'s "An account's opening balance lives on its Edit form" says so and cites
   pane A of
   [expense-world-person-opening-balance.html](../mockups/expense-world-person-opening-balance.html)
   in place of pane 5 of
   [expense-world-opening-balance.html](../mockups/expense-world-opening-balance.html), whose pane
   5 goes.
   *Passes if:* unit tests pin a person's form adding, changing and emptying its opening balance,
   and the screens match pane A of the mockup.
2. **`t` keeps the opening balance (builder).** `HAS_OPENING_BALANCE`'s app line and the
   opening-balance route's `PERSON_ACCOUNT` handling go from [errors.py](../../expense/errors.py)
   and [tui.md](../tui.md) ("`t` turns an account into a person and back", which drops its
   citation of screen 4 B, and the table in "When the engine says no");
   [test_errors.py](../../tests/unit/test_errors.py)'s rows for both go, and the comments heading
   those rows ("account-to-person 4 B" and "statement-code-field 3·2 B") say what the remaining
   rows prove; [test_tui_account_kind.py](../../tests/unit/test_tui_account_kind.py) loses its
   `HAS_OPENING_BALANCE` case and gains `t` on an account with an opening balance answering
   `Now a person.` The mockups `expense-world-account-to-person.html` and
   `expense-world-person-reconciliations.html`, which still draw the old refusal, are redrawn by
   [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md).
   *Passes if:* no code or doc names an app line for `HAS_OPENING_BALANCE`, or for
   `PERSON_ACCOUNT` on the opening-balance route, and the unit tests pin `t` turning an account
   with an opening balance.
3. **The live test of a person's opening balance (builder).**
   [test_opening_balance.py](../../tests/contract/test_opening_balance.py) proves a person from
   `POST /people` takes an opening balance (`201`, under `@Opening`, named by its
   `opening_balance_transaction_id`) and refuses a second (`409 OPENING_BALANCE_EXISTS`), where
   `test_a_person_names_no_opening_balance` pins the old rule; the `make-person` cases of
   [test_account_kind.py](../../tests/contract/test_account_kind.py) and the person rule in
   [test_people_lifecycle.py](../../tests/contract/test_people_lifecycle.py) are 2b's, which
   rebuilds them on cards; the clause of [runtime.md](../runtime.md)'s paragraph on this test
   follows, and its people clauses stay for 2b.
   *Passes if:* those live tests pass against the practice engine on `4ac20e42cf8566ee`.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `e06456a20aca6e4c` → `4ac20e42cf8566ee` (`d34fc8d06ff652c4`, `4ac20e42cf8566ee`).
- **The engine's "Done when" checks to report on:** the TUI has recorded contract
  `4ac20e42cf8566ee`; a person's opening balance can be added from the app, and make-person on
  an account with one succeeds.
- **The asks it closes:** none.
- **If question 1 is B,** the check "a person's opening balance can be added from the app" is
  reported as declined by the owner, with the reason.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **A live test of the sheet import giving a person its opening balance:** the import making an
  existing person's first `SALDO INICIAL` row its opening balance. The owner's import path does
  not exercise it, since people are turned into people after the import.
