# Amounts follow your number format

**Status: approved on 2026-11-08 on the recommended answers, on the mockup
[expense-world-number-format.html](../mockups/expense-world-number-format.html).** Tasks 4 and 5
wait on the engine ask "A user's settings hold their number format". When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The app reads and writes amounts one way only: a dot for decimals, a comma between thousands
(`1,234.56`). Someone who writes `1.234,56` cannot use it, and a decimal comma typed by habit is
read wrong without a word: `-1,5` saves -15.00. The format belongs to the person, not the device,
so it is kept on the account and every client follows it.

## What it must do

1. **Two formats:** `1,234.56` (dot for decimals) and `1.234,56` (comma for decimals).
2. **The format is a setting on the owner's account,** kept by the engine, set in the app on
   System ▸ Auth & profile.
3. **Every amount typed follows it:** the LOG bar, every form's amount line and every balance
   box. An amount that does not fit is never saved as something else.
4. **Every amount shown follows it:** lists, Home, statements, forms, toasts and the `?` card's
   examples. Amounts inside the engine's own words stay as the engine wrote them.
5. The files the importers send (the owner's sheet, a bank download, a statement PDF) are the
   engine's to read, and do not change.

## How the owner knows it is done

1. Under `1,234.56`, typing `-1,5` on the LOG bar is refused with a note naming the format, and
   nothing is saved; `-1,500` saves -1,500.00.
2. Picking `1.234,56` on System ▸ Auth & profile turns every amount on every screen into
   `1.234,56`, and `-18,50` on the LOG bar saves -18,50.
3. The pick holds after the app is closed and opened again, and on any other device.
4. The live contract suite proves the setting is saved, read back and cleared, and that an
   unknown format is refused.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Before a format is picked, which one is used? Mockup pane 1. | A: the device's region (this Mac: English (Peru), `1,234.56`); picking one on System ▸ Auth & profile makes every device follow it, and *Follow this Mac* clears it (2026-11-08). |
| 2 | An amount that does not fit the format, such as `-1,5` under `1,234.56`? Mockup pane 3. | A: refused, the note naming the format (`can't read -1,5 as an amount: amounts are 1,234.56`); nothing sent. A thousands mark is always followed by three digits (2026-11-08). |

---

## Tasks

Approved. Tasks 4 and 5 wait on the engine ask "A user's
settings hold their number format".

4. **The setting** (waits on the engine). The format on `GET /auth/me` wins over the region;
   System ▸ Auth & profile shows the `number format` row and `f` asks which one, saving through
   `PUT /auth/settings`, *Follow this Mac* clearing it; a refusal in the engine's words; amounts
   on screen follow the new format at once.
5. **The live contract tests** (waits on the engine): the setting saved, read back on
   `GET /auth/me`, cleared, and an unknown format refused.

## Found along the way

Not built in this spec; sorted when it is done.
