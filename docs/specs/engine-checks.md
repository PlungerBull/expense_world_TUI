# The app checks its engine

**Status: approved 2026-11-11 as tasks 5–7 of [The app the owner runs](going-live.md), split out
on 2026-11-12 into v1.2.**
- Its tasks wait on the engine's own going-live release. Its hand-off reaches
  [from-engine/](../from-engine/) as a catch-up file.
- Tasks 1 and 2 also wait on the owner picking their mockups.
- When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it is

The released `expense` knows which engine it talks to and says plainly what is wrong: a contract
it does not match, the real ledger or a practice one, the backup's age, and an engine that is down
or unhealthy.

## Owner's answers

1. **A contract mismatch:**
   - A change the engine marks as breaking (the first number of its `breaking.adding` contract version moves) opens one screen. It names both versions and what to do, and no other screen opens.
   - A change that only adds (the second number moves) opens the app as usual, with a one-line note.
   - The screen and the note are drawn as mockups, and the owner picks them before task 1.
2. **REAL or PRACTICE and the backup's age** always show on Home's top line, with the app's
   version: `REAL · backup 6 h ago · v1.0.0`. PRACTICE, and a backup older than 36 hours, show
   in the warning colour. The line is drawn as a mockup, and the owner picks it before task 2.
3. **The engine-down message names the engine's start command,** from the engine's operations
   guide. It is the one remedy that is not a screen, since no screen can start the engine.

## What it must do

1. **At launch the app checks the engine** against the contract version it last caught up to
   (the drift check's record). On a mismatch it does what answer 1 says, naming which side to
   upgrade.
2. **REAL or PRACTICE and the backup's age show** as answer 2 says, read from the engine's
   `/health`, never guessed from the address.
3. **An engine down or unhealthy is named with its fix**, on every screen:
   - down, as answer 3 says;
   - unhealthy, with the reason and fix the engine's `503` sends, shown as sent.

## How the owner knows it is done

1. The tester shows:
   - the mismatch screen against a practice engine on a different contract;
   - REAL and PRACTICE on the two engines;
   - a stale backup in the warning colour.
2. With the engine stopped, every screen names the fix.
3. Home shows the app's version, read from the installed package.

---

## Tasks

Each task leaves `pytest tests/unit` green.

1. **The launch check** and its screen. It waits on the engine's going-live release and the
   picked mockup.
2. **REAL/PRACTICE and the backup's age** on Home, with the app's version read at runtime from
   the installed package's metadata. It waits on the engine's going-live release
   and the picked mockup.
3. **The fix in every engine-down and unhealthy message.** The unhealthy half waits on the
   engine's going-live release.

## Found along the way

Not built in this spec; sorted when it is done.
