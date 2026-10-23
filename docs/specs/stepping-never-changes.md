# Stepping through a form never changes it

**Status: approved by the owner on 2026-10-23; the loop runs its tasks.** Drafted by the
orchestrator from the owner's three picks that day. The picks are drawn in
[mockups/expense-world-enter-and-esc.html](../mockups/expense-world-enter-and-esc.html) (both A).
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Pressing `⏎` to walk down a form should only move you along. Today it can do more: on the Edit
form's ACCOUNT or CATEGORY line it picks the first name in the list, so walking past a
transaction can move it to another account or change its category without your meaning to. On
the Edit form of an archived account's line in Reconciliations ▸ "no batch", where nothing can
change, typing still lands on a locked line, and `⏎` does not save when every line after it is
locked.

## What it must do

- **The Edit form's ACCOUNT and CATEGORY lines start on what the transaction has** (Question 1,
  pick A). Landing on either line, the highlight is on the transaction's own account or category,
  so `⏎` keeps it. Typing or `↑↓` still choose another. The same holds on the bank-line Edit form
  in "no batch", which shares the form.
- **On a split part, `esc` keeps the hashtags added with `⏎`** (Question 2, pick A). This is how
  the split screen works today; it gets a test and a line in [tui.md](../tui.md) so it stays.
- **An archived account's line opens with every line read-only** (the owner's pick, A). Nothing
  typed ever lands on a locked line, and nothing is sent.
- **`⏎` saves when no line ahead can change**, as [tui.md](../tui.md) "The bar forms' keys" says,
  on every bar form, not only on the last line of the sequence.

## How the owner knows it is done

1. On a transaction on Sueldo Soles in COMIDA, `⏎` on every line of its Edit form and then
   `ctrl+s` changes nothing: the toast says there is nothing to save.
2. On a split part, adding two hashtags with `⏎` and then pressing `esc` leaves both in the
   table.
3. On an archived account's line in "no batch", typing and `⏎` change no line, and nothing is
   sent.
4. On an archived account's line whose only open line is its empty operation code, typing the
   code and `⏎` saves it.

## Not in this spec

- **A non-date in the Edit form's date crashes the app** stays in [todo.md](../todo.md): its
  message is wording the owner picks first.

---

## Tasks

Approved by the owner on 2026-10-23.

1. **ACCOUNT and CATEGORY start on the current value.** On the Edit form and the bank-line Edit
   form, landing on ACCOUNT or CATEGORY puts the highlight on the transaction's own one, so `⏎`
   with nothing typed keeps it; typing filters the list as now. Passes if: unit tests show `⏎`
   through every line of an Edit form then `ctrl+s` sends nothing; `⏎` on an untouched ACCOUNT
   keeps the account; typing then `⏎` still picks the typed one; a row in @Pendiente starts on
   @Pendiente; [tui.md](../tui.md) says it.
2. **Pin `esc` keeping a split part's hashtags.** Passes if: a unit test adds two hashtags with
   `⏎` on a part's HASHTAGS line, presses `esc`, and finds both on the part in the table and in
   what `ctrl+s` sends; [tui.md](../tui.md)'s split screen keys say `esc` keeps what `⏎` added.
3. **Nothing lands on a locked line.** On an Edit form where every line is read-only, typing and
   `⏎` change no line. Passes if: a unit test on an archived account's line with title and
   operation both set types text and presses `⏎`, and the summary shows no typed value and
   `ctrl+s` sends nothing.
4. **`⏎` saves when no line ahead can change.** `FormScreen._advance` saves when every field after
   the current one is read-only. Passes if: unit tests show `⏎` on the only open line of an
   archived account's "no batch" line sends the save, and the same on Manage ▸ Accounts Edit
   after a failed opening-balance read; a form with an editable line ahead still moves to it.
