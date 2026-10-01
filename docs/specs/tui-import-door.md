# Import bank files from the TUI

**Status: draft.** The owner reviews and completes this spec before the loop starts on it.
How it gets built: [file-import-plan.md](../file-import-plan.md) §3. When done, the why moves to
[decisions.md](../decisions.md), and this file and that plan's §3 are deleted.

---

## What it must do

- In `expense world`, `+` opens the LOG bar. Dragging a BCP `.xlsx` onto the terminal, or
  pasting its path, turns the bar into "import this file". Several files at once work too.
- It then asks which account the file belongs to, **every time**. Nothing is remembered by file
  name, so a re-download named `… (1).xlsx` behaves like any other file.
- A preview shows each row as new or already in the ledger. Nothing is written until the owner
  confirms.
- New rows land under `@Pendiente`, to be classified in Home as today.
- After applying, the "may be logged twice" note speaks about what just happened ("check it and
  delete the extra one"), not "before `--apply`". The typed `expense import bank` gets the same
  fix.
- It works in Terminal.app and in VS Code's terminal.

It is used for real only after [official-migration.md](official-migration.md) is done.

## How the owner knows it is done

1. Drag a bank download onto `expense world` in Terminal.app, then in VS Code: both open the
   import.
2. Pick the account; the preview marks rows already in the ledger; apply.
3. The new rows show in Home under `@Pendiente`.
4. Import the same file again: every row reads as already in the ledger, nothing is added.

## Open questions for the owner

### The screens
Asked 2026-09-30
Drawn in [expense-world-import-door.html](../mockups/expense-world-import-door.html): drop the
file, pick the account, the preview, the result. Screens 1–3: fine as drawn, or what changes?
Screen 4, the "may be logged twice" note after importing:
- **A.** The same words as the preview.
- **B.** "1 day where the ledger may now hold the same movement twice — check it and delete the
  extra one".

**Recommended:** B. It names the problem and the fix.

## Tasks

Draft, for the owner's approval.

1. The owner picks the mockups (**[UI] gate**).
2. Recognise a dropped or pasted path, in each terminal's format.
3. The import screens: account list, preview, apply, reusing the typed import's engine call.
4. Stop remembering accounts by file name; remove that saved setting.
5. The after-apply wording, in both the TUI and `expense import bank`.
