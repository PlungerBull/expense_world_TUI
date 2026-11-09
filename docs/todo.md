# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks wait in [to-engine/](to-engine/), one file each, until
handed over.

---

## Queue

Approved specs, in the order the loop runs them (CLAUDE.md "Specs and tasks"). A spec joins
when the owner approves it and leaves when it retires; one that is blocked says on what, and the
loop skips it until it can run.

1. [The app on contract `2fa4967b8eed9c3f`: an account's kind, strict requests and the closed-day refusals](specs/catch-up-to-2fa4967b8eed9c3f.md):
   approved 2026-11-08. Its last task waits on the owner ("Task 5 of the catch-up hit four review
   rounds"); its acceptance check, sweep and reply follow it.
2. [The cash account](specs/the-cash-account.md): approved 2026-11-08.
3. [Closing a month with leftover lines](specs/closing-with-leftover-lines.md): approved
   2026-11-08. Tasks 1 and 2 wait on the engine ask "A loose-lines refusal names its lines by id,
   in a field a client reads".
4. [Amounts follow your number format](specs/amounts-follow-your-number-format.md):
   approved 2026-11-08. Tasks 1–3 done; tasks 4 and 5 take the engine's hand-off of 2026-11-08
   (`2fa4967b8eed9c3f` to `9b3b43429d8bd11e`), which also covers `c15201ee50485e56`.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes it. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### Task 5 of the catch-up hit four review rounds: finish it or trim it?
Asked 2026-11-09 · Blocks: task 5 of [the catch-up](specs/catch-up-to-2fa4967b8eed9c3f.md)
Task 5 proves every request the app sends fits the engine's stricter rules. The app already does,
and needed no change. The tests also added a guard that fails any future test sending a malformed
request; four reviews in a row found one more corner where that guard was stricter or looser
than the engine (the last: it calls `5.0` malformed, which the engine accepts). The work is kept
aside, unchanged, in git's stash, named "catch-up task 5 (strict requests), parked after 4 review
rounds".
- **A.** A fresh builder finishes it: the two-line fix the last review named, one more review.
- **B.** Keep only the plain tests (the app's requests checked once) and drop the always-on guard.
**Recommended:** A, because the fix is named and small, and the guard keeps every later change
from sending a request the engine refuses.

### Three small screen questions from the finished catch-up
Asked 2026-11-09 · Blocks: nothing yet; each joins a spec in its area once answered
Found while the catch-up to `1002f105c6bacdf1` ran; sketches come with the next summary.
1. **`n` on Manage ▸ Accounts while the list shows "Could not load."** It opens a New form whose
   currencies line has nothing to pick (the currencies come with the list's read). Turn `n` off
   until the list loads, or keep it?
2. **A flagged line in a currency a one-currency paper does not cover** shows in the preview's
   `⚑` block with no currency (the column shows only on a two-currency paper). Leave it, show the
   currency on such lines, or show the column whenever the paper misses a currency?
3. **The `⚠` notes:** the preview leads each with its currency (`⚠ USD: …`), the close screen
   leaves a covered currency's bare. One way on both screens, or each as it is?

### Small screen details from the account numbers work
Asked 2026-11-09 · Blocks: nothing; each answer other than "as built" joins a spec in its area
Found while accounts got their numbers; each is built as described, against the mockup
[expense-world-account-numbers.html](mockups/expense-world-account-numbers.html); sketches come
with the next summary.
1. **A New bank account left before the engine refuses it** reads `Not created · Account
   (unnamed)`, since the account has no name until the engine builds it. Keep it, or name it by
   the bank typed (`Account BCP`)?
2. **Removing a card** asks `Remove card 5678 from BCP-5678?` / `1234 is its number again. No
   screen can bring 5678 back.`; the mockup also said `and it shows as BCP-1234`, which only the
   engine can say. Keep it, or ask the engine for the name a removal leaves? Its footer is every
   question's `[y] confirm [enter / n / esc] cancel`, not the mockup's `y removes · any other key
   keeps it`.
3. **Lines the mockup did not draw:** the Edit form's `since` leaves the form while the account has
   no number, and so does `new card`; `new card from` shows once `new card` holds digits; several
   older cards share one `cards before` line, oldest first; the new lines' hints follow the
   form's others (`optional · the replacement card's last 4 digits · enter to go on`). Keep them?
4. **The LOG bar's `$` hint lines:** the mockup drew `"$5678" matches 1 account` and `$56 is an
   amount: 56.00`; today a single match resolves as you type with no line, as `$nic` does, and no
   amount line shows. Add both lines, or keep it as it is?
5. **The upload could skip "Which account is this statement?"** now that accounts carry their
   numbers: the engine would name the account from the number the paper prints. Ask the engine
   for it, or keep asking?
**Recommended:** 1–4 as built, since each follows the app's existing screens and builds no name
in the app; 5 ask the engine, since the paper already says which account it is.

[The official import](specs/before-the-official-import.md) is rewritten for built names now that
the numbers spec is done, and comes for approval with the next summary.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **After a reload that fails, the ledger's footer and `?` card keep its row keys** (`a`, `c`,
  `b`, `h`, `m`, `s`, `d`) with no list on screen, since `TransactionsScreen.has_rows`
  (`expense/tui/screens/transactions.py`) reads the rows read before; the Manage lists drop them.
- **Small test cleanups from the catch-up to `1002f105c6bacdf1`:** test_account_create.py's
  shape-first docstring names "a person's empty name" though every body there is a bank account;
  `test_day_of_reads_the_users_zone_whatever_the_machine_zone_is` (test_fake_engine_answers.py)
  calls `monkeypatch.undo()`, lifting the autouse guards for the rest of that test;
  `_CLOSE_NOTES`' lists in helpers.py are one object shared by every upload answer; two test names
  say "the engine's words" (test_cmd_import.py:602, test_tui_bank_import.py:1164) though the row
  text is a stand-in.
- **Small test cleanups from the account numbers work:** the Edit form lands no `color` refusal,
  and a few refusal tests put a raw string in `_values` (test_tui_opening_balance.py:514, :712);
  no test proves a pick change or typing hides a line's refusal in `t`'s question
  (test_tui_account_question.py:317), whose `written()` repeats `_currency_write`'s
  (accounts.py:317, :382); the quit-question test of a number refusal waits on two pauses
  (test_tui_quit_asks.py:545-548); no screen test covers `↵` on a typed `$bcp` taking the first
  entry (test_tui_log_bar.py); the live suite pins neither the PDF's group-line number check
  (`card_paper` prints no group line) nor the edit's `ID_EXISTS` and `CURRENCY_NOT_HELD` on
  `opening_balances`; two module docstrings overstate their tests (test_statement_numbers.py:15-16,
  test_account_one_write.py:16-18); `_bank_account` (test_account_numbers.py:41-51) repeats
  `scratch.account`.
- **Two comments in expense/errors.py (:71, :328) cite `POST /v1/accounts/{account_id}/opening-balance`,**
  which the account Edit form no longer uses; point them at `PUT /v1/accounts/{account_id}` if
  they describe it.
- **`scripts/clean_practice_user.py` cannot remove an unnumbered `BCP`** a killed live run leaves
  behind (`owns` matches bank accounts by a number starting 9), so later runs hit `NAME_EXISTS`
  until it is deleted by hand.
- **No list test renders an engine-sent total past the largest amount;** only the formatter and a
  typed opening balance are proven.
- **The upload preview's page budget counts each `⚠` note as one line,** though a long one wraps
  on a narrow window.
- **Bank files become the intake.** Plan: [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` opens the LOG bar inside the app.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **The "no statement" list under 68 columns.** The Statements screen's list of lines in no
  statement cuts its amount, then its currency, under 68 columns, and under 62 its caption wraps a
  lone `·` onto a line of its own. Parked 2026-11-07: the app is built for 80 columns.
- **`b`'s note when moved rows came from several currencies** gives one sentence per currency, a
  case the engine's two currencies cannot reach; confirm its wording with the owner when a third
  currency comes.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
