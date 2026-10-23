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

1. **The drift script reads a test's paste event as engine fields.** The acceptance check of
   2026-10-23 failed on `scripts/check_fixture_drift.py`: `tests/unit/test_tui_edit_form.py`
   line 1673 builds a stand-in paste event, `type("Paste", (), {"text": ..., "stop": ...})`, and
   the script reports `text` and `stop` as fields the engine no longer has. Passes if: the test
   pastes through Textual's real `events.Paste` (the reviewer's note on task 3), still proving a
   paste lands nothing on a locked line, and the drift script against the practice engine exits
   clean.
