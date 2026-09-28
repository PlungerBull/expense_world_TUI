# Spec: catch up with the engine's error reasons

Written 2026-09-28, drafted by the orchestrator and approved by the owner.

## Why

The engine's published contract moved from the version this repo last checked
(`9d593f48328c0c6a`); the practice engine reported `ef2132c3c3b2ff6f` on 2026-09-28, and the
engine team's note names `fa88ffe22f4e86f2`. Every engine error now carries a reason per field
(`error.reasons`, for example `RANGE_INVERTED`, `PERIOD_OVERLAPS`, `SEALED_PERIOD`, `LOCKED`),
and the engine says to decide on those reasons, never on the wording of its messages. It also
reworded some messages and moved one batch error onto the row it belongs to.

Today the CLI picks some of its hints by searching the engine's message wording: the two
reconciliation period refusals, the two ways completing a reconciliation is refused, and the
hint for editing a row that a completed period locks. The engine no longer promises that
wording, so a rewording could silently break those hints, for this client and for the web and
iOS clients that copy the pattern. Both of this repo's open engine asks have landed with this
version.

## What must be true when it is done

1. **Hints are chosen by the engine's reasons, never its wording.** Every place the CLI or the
   TUI decides something from an engine error decides it from `error.reasons` (or the status
   and error code), not from `message` or the text of `fields`.
2. **What people see does not change.** Every error shows the engine's message, each field's
   message and the same hint as today. Reason codes are not shown on screen. `--json` still
   prints the engine's error exactly as sent, reasons included.
3. **Batch and import errors land on the right row.** An unknown hashtag in a batch now comes
   back on its own row (`transactions.<index>.hashtag_ids`), like every other field. The bank
   import, the sheet import and the LOG bar name the refused row for it, as they already do
   for other fields.
4. **Nothing depends on the old wording.** No code relies on the `"Value error, "` prefix, the
   old monthly-report messages, or "sealed" being reported ahead of a future date in a batch.
5. **The test data matches the engine.** The engine replies the unit tests fake carry `reasons`
   where the engine sends them, and the fixture check passes against the practice engine.
6. **Citations and asks catch up.** Comments that cite the rules now cite the new contract
   parts (for example the create operation's validation list and "Error reasons"). Both engine
   asks are deleted, since they landed.
7. **The new version is recorded** only when all of the above is done, and the version check
   then passes quietly. If the engine has moved again by then, what the newer versions changed
   goes to the owner first, as for any moved version.

## How the owner knows it is done

- A search of the code finds no hint chosen by matching the engine's message wording.
- Every error looks the same as before.
- The version check against the practice engine passes with nothing to report.
- `docs/engine-asks/` holds only the test-engine ask.

## Not in this spec

- Showing reason codes on screen (decided 2026-09-28: errors look as they do today).
- Any other command, screen or engine change.

## Tasks

Drafted by the orchestrator and approved by the owner 2026-09-28. One at a time, in this
order. Each is deleted here in the commit that finishes it. The practice engine (`:8002`) runs
the new contract; the builder may read `/openapi.json` there (the "Error reasons" section and
each operation's `x-error-reasons`).

All tasks are done. Next: the tester's acceptance check, then the librarian's sweep
(CLAUDE.md "How work runs", "Per spec").
