# A save that answers after you leave its screen

The Backlog run of 2026-11-05 found this while it moved the app's background work onto one
shared hand-back: you can leave a screen (`esc`) while its save is still on its way to the
engine, and when the engine answers, the app says nothing.

**Status: every question answered, the mockup picked and the tasks and their words approved on
2026-11-06; the loop is running.** It waits on no other spec.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

A save, a delete, a bulk edit or a statement action runs in the background. If you press `esc`
before the engine answers, the screen closes. When the engine answers, the app drops the answer:

- If the save landed, you see no "Saved." and no "Account created.". It did save.
- If the engine refused it, you never see the refusal. The change did not happen, and nothing
  says so.
- A bulk edit you leave mid-run does not say which rows changed and which were refused.
- The account form saves the account first and then each opening balance. Leave it after the
  account saves and the opening balances after it are never sent, and nothing says so.

## What it must do

1. **A save you left still tells you how it ended**, as question 1 picks.
2. **The account form never loses an opening balance without saying so**, as question 2 picks.

## How the owner knows it is done

1. Leave a form while it saves: the app tells you how the save ended, as question 1 picks, both
   when it lands and when the engine refuses it.
2. Leave the account form while it saves an opening balance: what happens is what question 2
   picks.
3. The unit suite passes.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | You leave a screen before its save answers. What does the app show when it answers? | The message the screen would have shown: "Saved.", "Account created.", or the engine's refusal in full; for a bulk edit, the receipt and each refused row (2026-11-06). |
| 2 | The account form, left while it saves its opening balances? | You leave, the opening balances still go, and you are told how each ended (2026-11-06). |
| 3 | The mockup, [expense-world-save-after-leaving.html](../mockups/expense-world-save-after-leaving.html) | 2B a refused save's message is titled with what was not saved (`Not saved · Wong · -45.90`), stays 10 seconds and ends `Nothing was saved: open it again to fix it.` · 3B a bulk edit's refused rows are named by date, title and amount, the first four and `and N more` · 4B after you leave, each write still waiting still goes, a refused one stopping none after it, and the message says how each ended (`Not all saved · Account BCP 5678`); the same for a statement's ticks · 5B a statement completed after you left says `Statement completed · SIG-202610`, its `⚠` notes and `⚑ 3 lines flagged for review: open the statement and press f.`, and opens no screen · 6B balances saved after you left say `Balances saved · SIG-202611` and `The statement is not completed: open it and press c.` (2026-11-06). |
| 4 | The account Edit form's message after you leave it, in the cases the mockup does not draw? | One line per part, saved or not, in the order sent: `The account's changes are saved.` / `are not saved:` and the engine's words; `The PEN opening balance is saved.` / `is not:`; an emptied one `is deleted.` / `is not deleted:`; then `Open the account's Edit form to set <its changes, PEN, …> again.` naming what is left. All refused is titled `Not saved · Account …` (2026-11-06). |

---

## Tasks

Approved on 2026-11-06. Each task's "passes if…" is written when it starts. "Left" means the
screen that sent the write has closed before the engine answered; on a screen still open,
nothing changes.

A write opts in by carrying its refused message's first line (a `LeftBehind` on `run_write` and
`confirm_delete` in `expense/tui/screens/_base.py`); every write but a statement's complete and
its balances already does; a save of several writes reports once (`SaveReport`).

8. **A statement's complete and its balances** (panes 5 B and 6 B): `Statement completed ·
   SIG-202610` with its `⚠` notes and the `⚑` line, opening no screen; `Balances saved ·
   SIG-202611` and `The statement is not completed: open it and press c.`

**Words to approve with the tasks:** a refused message's first line is what did not happen, then
`·` and what it was. The mockup draws `Not saved`, `Not created`, `Not deleted`, `Not archived`
and `Not all saved`; the others follow the same way: `Not unarchived`, `Not made a person`, `Not
made a bank account`, `Not added · PEN on BCP 4471`, `Not removed · PEN on BCP 4471`, `Not
provisioned`, `Not ticked` and `Not unticked` for a statement's line, `Not reverted`, `Not
completed`. A transaction is named `<title> · <amount>`, an account `Account <name>` (`Person
<name>` for a person), a category `Category <name>`, a hashtag `Hashtag #<name>`, a statement
`Statement <name>`.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- The account form saves the account and each opening balance as separate writes, so every
  client must chain them and say how each ended. One engine write taking both would let a save
  land whole or not at all: an engine ask.
- Quitting the app (`ctrl+q`) while saves still wait to be sent drops them, and nothing says
  so; this spec keeps quitting as it is.
- `(unnamed)` for a blank name is written out in four places (`not_done_line` and the account,
  category and hashtag lists); `title_or_untitled` is the one shared copy for titles, and names
  have none.
- After you leave, a write that failed with a `5xx` or got no answer may still have landed. The
  Edit forms then leave out their "open it again" line, but the Manage forms and the account
  Edit form still end with theirs ("Nothing was saved: open it again to fix it.", "Open the
  account's Edit form to set PEN again."), which may be untrue.
- Small code finds in the after-leaving code: `_landed_after_leaving` in create_forms.py reads
  `left_behind.part.report` unguarded; `ReportedPart.record` writes `SaveReport`'s private
  `_answers`; `_opening_saved`'s `part` has no type; no test drives the real `esc` (the tests
  pop the screen); no test covers an account save whose only write is the account; the test of
  a new statement created after leaving calls `_created` by hand instead of driving the late answer.
- The delete question's line (`Delete this transaction?` over `Sueldo · 800.00 · …`,
  `delete_row_line`) writes an income without the `+` the ledger shows it with.
