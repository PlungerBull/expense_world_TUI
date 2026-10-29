# The practice engine serves only the engine's shipped code

Catches up to contract `e020782e3579d011`, from `256f3190cf24fc36`: the parts of the engine's
hand-off of 2026-10-28, "A person is a holder; unpairing is one write; the PDF upload moves a line
one day off; the change log reaches back; your practice engine serves only shipped code", on the
practice engine and the change log (`95e8fea031ba6bd1` and `e020782e3579d011`), and the two fields
its other parts make the test answers lack. Its other parts are in
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
[catch-up-cards-statements-2c-live-suite-holder-move.md](catch-up-cards-statements-2c-live-suite-holder-move.md),
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

**Status: draft, written 2026-10-28 for the owner to rewrite or approve; no question waits on the
owner. Its tasks are drafted and wait on the owner's approval.** It runs after
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md)
and before [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
whose live tests then run on shipped code. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The practice engine is the copy of the engine every check of this app runs against. Today it is
started from the engine's checkout as it stands, so it serves the engine coders' unfinished work
too. On 2026-10-28 that went wrong twice: this client recorded a contract version that never
shipped (`f00534abdde7fa82`, a draft of `256f3190cf24fc36`), and a restart failed while the engine
coders were mid-edit. The engine now ships a launcher that serves only its last commit, and its
change log reaches back to `46e2fdf6e11d7548`, so every version this client records is one the
log lists. Nothing you see in the app changes.

## What it must do

1. **The practice engine is started by the engine's own launcher,** which serves only the
   engine's last commit, on :8002 over the disposable test database, and stopped by its process;
   the practice users are reseeded and their keys printed to the terminal as today.
2. **The session guard lets agents start and stop the practice engine only that way,** and
   [runtime.md](../runtime.md) "Working against the live engine" says how.
3. **A contract version is recorded only when the engine's own change log lists it,** so a draft
   is never recorded.
4. **The test answers carry the fields the contract now requires:** a holder's kind
   (`is_person`) and the PDF upload's `redated` on each row and in its counts
   (contract: "Holders", "Its kind") (contract: POST /v1/statements/import).

## How the owner knows it is done

1. After the practice engine starts, the version check names the newest version in the engine's
   change log and passes, and the fixture check names nothing.
2. Recording a version the change log does not list is refused, and records nothing.
3. The unit suite passes.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-28; they wait on the owner's approval. Each leaves `pytest tests/unit` green.

1. **The launcher (builder).** `scripts/practice-engine up` starts the engine with the engine's
   client practice launcher, given the port 8002, from the engine checkout's root (the hand-off's
   section 11 names its path and its refusals), detached as today, and knows it again on :8002 by its command; `down` stops it by its pid; the reseed and
   the keys stay as they are, and nothing from the caller's environment reaches it.
   *Passes if:* `up` then `down` start and stop it, the version it serves is the newest in its
   change log, and anything else on :8002 is left alone.
2. **The guard (builder).** `.claude/hooks/guard.py` lets the tester start the practice engine
   only with the launcher and stop it only by its pid, as runtime.md says; its tests trip each
   rule, the old start included; runtime.md "Working against the live engine" says how.
   *Passes if:* the hook tests pass, and runtime.md names no start command but the launcher.
3. **Record only a listed version (builder).** `scripts/check_fixture_drift.py
   --record-version` refuses a served version its own `x-changelog` does not list, records
   nothing, and says why; runtime.md "Contract version" says so.
   *Passes if:* a test proves the refusal and that a listed version is recorded.
4. **The test answers' new fields (builder).** In tests/unit/helpers.py, `holder_list` and
   `holder_record` carry `is_person` and the upload's answer carries `redated` on each row and
   `counts.redated`; no screen changes.
   *Passes if:* the drift check against the practice engine names no missing field.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the last spec of the range
`4dd95f836dba7be2` → `e020782e3579d011` is done, with the tester's results.

- **Range:** `95e8fea031ba6bd1` and `e020782e3579d011` of the hand-off "A person is a holder; …"
  (its sections 10 and 11).
- **The engine's "Done when" checks to report on:** the TUI's practice engine is started by the
  engine's client practice launcher on port 8002, and the version it records is always one listed
  in `x-changelog`.
- **The asks it closes:** "Keep every change-log entry in the contract".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
