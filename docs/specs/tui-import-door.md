# Import bank files from the TUI

**Current spec** (owner, 2026-10-02).
How it gets built: [file-import-plan.md](../file-import-plan.md) §3. When done, the why moves to
[decisions.md](../decisions.md), and this file and that plan's §3 are deleted.

---

## What it must do

- In `expense world`, `+` opens the LOG bar. Dragging a BCP `.xlsx` onto the terminal, or
  pasting its path, turns the bar into "import this file". Several files at once work too, in
  Terminal.app; VS Code's terminal takes one file per drop, so there they go one at a time.
- It then asks which account the file belongs to, **every time**. Nothing is remembered by file
  name, so a re-download named `… (1).xlsx` behaves like any other file.
- A preview shows each row as new or already in the ledger. Nothing is written until the owner
  confirms.
- New rows land under `@Pendiente`, to be classified in Home as today.
- After applying, the "may be logged twice" note reads "1 day where the ledger may now hold the
  same movement twice — check it and delete the extra one", with the day's lines under it, not
  "before `--apply`". The typed `expense import bank` keeps its wording: it is deleted once this
  door ships ([tui-only-plan.md](tui-only-plan.md)).
- The screens are the mockup
  [expense-world-import-door.html](../mockups/expense-world-import-door.html): screens 1–4
  approved (4: B, 5: A, 6: A, 7: B).
- It works in Terminal.app and in VS Code's terminal.

It is used for real only after [official-migration.md](official-migration.md) is done.

## How the owner knows it is done

1. Drag a bank download onto `expense world` in Terminal.app, then in VS Code: both open the
   import.
2. Pick the account; the preview marks rows already in the ledger; apply.
3. The new rows show in Home under `@Pendiente`.
4. Import the same file again: every row reads as already in the ledger, nothing is added.

## Tasks

From the acceptance check (2026-10-02):

1. Record contract 8d2430081e64cd7c (owner, 2026-10-02: catch up later, in
   [engine-catch-up-8d243008.md](engine-catch-up-8d243008.md)). The fixture check flags three test-only keys: `enter` and `escape` (Textual key names in the
   import door's footer asserts) and `sheet_account_names` (the config test). Add each to
   `KNOWN_LOCAL` in [scripts/check_fixture_drift.py](../../scripts/check_fixture_drift.py) with
   what it is, so the check passes on a matching version.
