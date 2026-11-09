# Amounts follow your number format

**Status: approved on 2026-11-08 on the recommended answers, on the mockup
[expense-world-number-format.html](../mockups/expense-world-number-format.html); its last two tasks
take the engine's hand-off of 2026-11-08, contract `2fa4967b8eed9c3f` to `9b3b43429d8bd11e`.** When done, the why moves to
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

## What the engine declined, or did differently

- **A format other than the two is refused `INVALID_FORMAT`,** not a reason of its own: the
  engine has one reason per rule.
- **Sign-up takes no format:** `POST /auth/bootstrap` refuses `number_format` (`UNKNOWN_FIELD`);
  a new user reads `null` until they pick one.
- **`null` clears the pick,** unlike `display_timezone`, whose `null` is refused.
- **Also in the hand-off, nothing to build:** a timezone is stored and answered in its listed
  spelling (`america/lima` reads back `America/Lima`), and a reused token id's message names "a
  personal access token". The app compares neither.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Before a format is picked, which one is used? Mockup pane 1. | A: the device's region (this Mac: English (Peru), `1,234.56`); picking one on System ▸ Auth & profile makes every device follow it, and *Follow this Mac* clears it (2026-11-08). |
| 2 | An amount that does not fit the format, such as `-1,5` under `1,234.56`? Mockup pane 3. | A: refused, the note naming the format (`can't read -1,5 as an amount: amounts are 1,234.56`); nothing sent. A thousands mark is always followed by three digits (2026-11-08). |

---

## Tasks

Approved. Each reads the live contract on the practice engine before building.

All done; the acceptance check, the sweep and the reply follow.

## Reply to the engine

The reply to the hand-off "A user's settings hold their number format, a timezone is stored in
its listed spelling, and a reused token id names the token in words" (2026-11-08, `2fa4967b8eed9c3f`
to `9b3b43429d8bd11e`). It reports on its "Done when" checks, a pick made on one device showing
on another and the practice runs passing on `9b3b43429d8bd11e`, any contract problem found, and
closes the ask "A user's settings hold their number format".

## Found along the way

Not built in this spec; sorted when it is done.

- **After Setup connects, the account's number format waits for the next launch:** a new
  device follows its region for its first session (expense/tui/screens/setup.py reads
  `/auth/me` already).
- **A format saved after leaving Auth & profile** sets the session format and says `Number
  format saved.`, but Home, already reloaded in the old format, keeps it until its next load;
  no left-behind write reloads the screen under it (`_write_finished_after_leaving` in
  expense/tui/screens/_base.py).
- **The new wording on Auth & profile:** the toast `Number format saved.`, and the row
  `1,234.56  · follows this Mac` with no region named when the Mac's region cannot be read.
- **Small test and code cleanups:** the `follow-this-mac` case of
  `test_enter_saves_one_put_with_the_exact_body` starts on the format it ends on, so it proves
  the `null` body but not the switch back; the launch read takes no `verbose`
  (expense/tui/app.py); `AuthScreen.check_action` returns `True` rather than the base's answer.
- **Small cleanups in tests/contract/test_number_format_setting.py:** the comment above
  `CREATED = 1` cites "Response fields" where the numbering lives in "Activity Log", "Action
  codes"; the cleanup's `except Exception` could catch the expected 404 alone; "mints nothing"
  is proven for a live token's id but not a revoked one's.
