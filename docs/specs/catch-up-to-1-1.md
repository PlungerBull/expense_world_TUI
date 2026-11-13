# Catch-up to contract 1.1

Catches up from contract `3a4ff8dac458cf83` through `1.0` to `1.1`.

**Status: approved 2026-11-12, with its tasks below.** It runs first in
v1.0. The engine's hand-off asks no question back. When done, its why moves to
[decisions.md](../decisions.md), its reply goes to [to-engine/](../to-engine/), and this file is
deleted.

---

## What changed

1. **The contract version is two numbers, `breaking.adding`** (contract: "Base Conventions").
   The first number moves on a change that can break an older client; the second on an addition.
   A client built against `X.Y` works against any `X.Z` with `Z` at least `Y`, as long as it
   ignores the fields, enum values, error codes, reasons and statuses it does not know. The
   version check keeps comparing the version as an opaque string.
2. **`GET /health` says what the engine runs:** its release, the contract version, `REAL` or
   `PRACTICE`, the database's structure updates, and the last good backup with its state and
   age. Every field is always present and `null` when unknown, which means unknown, never zero.
3. **`GET /health` answers `503 SERVICE_UNAVAILABLE` also when the database's structure no
   longer matches the engine's code,** with a `message` meant to be shown as sent. The engine also
   refuses to start on such a database.

## What the engine asks the TUI to do

1. Read the version as `breaking.adding`, store the version it was checked against, and compare.
2. Show `mode` and the backup's state and age from `GET /health`; optionally `release` and
   `contract_version`.
3. On a `503` from `GET /health`, show its `message` exactly as sent.
4. Run the practice engine on the new code.

1–3 are screens: they are [The app checks its engine](engine-checks.md)'s tasks 1–3, in v1.2,
each waiting on its mockup. 4 is done: `scripts/practice-engine up` starts the engine's own
launcher on its newest code, and the version check ran against it on 2026-11-12.

## How the owner knows it is done

1. The version check against the practice engine passes, with `1.1` recorded.
2. A live contract test shows `GET /health`'s fields and the `503` shape on the practice engine
   (`PRACTICE`, `not_kept`).
3. `pytest tests/unit`, the live contract suite and the drift script pass.
4. The reply to the engine is in [to-engine/](../to-engine/).

---

## Tasks

Each task leaves `pytest tests/unit` green. Task 1 is done.

2. **A live contract test for `GET /health`:** every field present, `mode` `PRACTICE` and
   `backup.state` `not_kept` on the practice engine, nulls allowed where the contract allows
   them. The `503` on a structure mismatch cannot be caused from this client, so it is cited,
   not driven.
3. **CHANGELOG's "Upgrading:" line** names contract `1.1` as the one the engine must serve.

## Reply to the engine

- **Range:** `3a4ff8dac458cf83` → `1.0` → `1.1`, read in full.
- **Done when, reported back:**
  - the TUI accepts `1.1` and its version check passes against it (task 1);
  - `mode`, the backup and the `503` message on screen arrive in v1.2, with
    [The app checks its engine](engine-checks.md); the live test (task 2) already reads them.
- **Asks it closes:** none.

## Found along the way

Not built in this spec; sorted when it is done.
