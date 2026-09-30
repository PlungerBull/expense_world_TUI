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
Asked 2026-09-29
Nothing is drawn yet: the account list, the preview, the result, and the after-apply note. The
mockups come first; the owner picks. With the new names, the two current accounts show
separately (`Sueldo Soles`, `Cuenta Digital Dólares`) and the card's two legs fold into one
line (`VISA Infinite Sapphire  PEN + USD`).

## Tasks

Draft, for the owner's approval.

1. Draw the mockups; the owner picks (**[UI] gate**).
2. Recognise a dropped or pasted path, in each terminal's format.
3. The import screens: account list, preview, apply, reusing the typed import's engine call.
4. Stop remembering accounts by file name; remove that saved setting.
5. The after-apply wording, in both the TUI and `expense import bank`.
