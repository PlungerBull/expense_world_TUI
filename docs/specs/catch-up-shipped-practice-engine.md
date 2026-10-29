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

**Status: approved by the owner on 2026-10-28, its tasks with it.** It runs after
part 1b, the statement screens (done on 2026-10-28)
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

Drafted 2026-10-28; approved by the owner on 2026-10-28. Each leaves `pytest tests/unit` green.

Tasks 1, 2 and 4 are done (2026-10-28): `up` starts the engine's launcher, the guard lets the
tester start the engine only with it, and the test answers already carried `is_person` and
`redated`, the drift check naming nothing.

3. **Record only a listed version (builder).** `scripts/check_fixture_drift.py
   --record-version` refuses a served version its own `x-changelog` does not list, records
   nothing, and says why; runtime.md "Contract version" says so.
   *Passes if:* a test proves the refusal and that a listed version is recorded.

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

- The comment at the start script's `$!` capture calls that pid "the backgrounded subshell";
  after the fork and exec chain it is the launcher's own pid, and the line runs past 100
  characters. Found by task 2's review.
- The guard's exemption that keeps the launcher's name, `client-practice-engine`, from counting
  as the start script's lets a name built from it at run time through
  (`x=client-practice-engine; scripts/${x#client-} up`). Names built at run time are a limit the
  guard's docstring already states, and a static spelling is still caught. Found by task 2's
  review.
- [test-suite-leftovers.md](test-suite-leftovers.md) point 11, "The guard checks a test-engine
  start whole", is about the old hand start, which the guard now blocks entirely; the owner's
  draft needs that point dropped. Found by task 2's review.
