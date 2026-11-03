# What the live tests for an account's currencies turned up

What part 5 of the catch-up to contract `f82426fb0a099676`, the live tests for an account's
currencies (done on 2026-11-02), turned up while it ran.

**Status: approved by the owner on 2026-11-02; no questions; its tasks wait on the owner's approval.** It runs
after part 6's leftovers (done on 2026-11-02) and before
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md). When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Two gaps in the tests, no change to anything you see:

- **The live suite reads the history entries of most account writes, not all.** It reads those
  of making an account, editing it, archiving it, turning it into a person, and adding and
  removing a currency. It does not read those of deleting an account, unarchiving it, or turning
  a person back into a bank account (contract: GET /v1/activity, "Accounts and their currencies").
- **No unit test shows how removing a currency on Manage ▸ Accounts draws the engine's two "not
  found" answers**, "account not found." and "currency <code> not found.", which the engine gives
  before any other refusal of a removal.

## What it must do

1. **The history entries of a delete, an unarchive and a turn back into a bank account** are read
   live, counted exactly, each snapshot with the contract's keys, as the other account writes'
   are.
2. **A unit test pins how `x` on Manage ▸ Accounts shows each of the two "not found" answers**:
   the engine's words, nothing written, as the screen shows its other refusals.

## How the owner knows it is done

1. The live suite passes against the practice engine, these tests included, and leaves nothing on
   either practice user.
2. The unit suite passes.

## What the owner settled

None: this spec changes only tests.

## Questions for the owner

None.

---

## Tasks

1. **The live suite reads the history of a delete, an unarchive and a turn back into a bank
   account.** In [test_account_reads.py](../../tests/contract/test_account_reads.py), next to
   `test_an_edit_an_archive_and_a_kind_change_each_log_the_account_alone`, through the shared
   `scratch` helpers. Passes if: the new test(s) read `GET /activity?resource_id=<account id>`
   after each of the three writes and count the entries exactly as the live contract states
   them (contract: GET /v1/activity, "Accounts and their currencies"), each snapshot carrying
   the contract's keys as the other account writes' tests check them; the module docstring's
   "What it leaves out" no longer lists these three; every citation added resolves against the
   live contract; the file passes against the practice engine and leaves nothing on either
   practice user. Reviewer: the counts come from the live contract, not from what the engine
   happened to answer; no body is built by hand.
2. **A unit test pins how `x` shows the two "not found" answers.** In
   [test_tui_account_currency_removal.py](../../tests/unit/test_tui_account_currency_removal.py),
   as cases beside the other refusals of `test_a_refusal_shows_the_engine_words_alone_and_the_list_stays`
   or a test of their own. Passes if: for "account not found." and for "currency <code> not
   found." (each in the error shape the live contract gives that route,
   contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}), the "Failed" note is
   the engine's words as sent, the removal is the only call, the list is not read again and
   `x` works again; the fixture check passes on the new answers. Reviewer: no app code changes;
   the answers' shape matches the contract, not a guess.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
