# The contract version is two numbers, and `GET /health` reports what the engine runs and answers `503` on a structure mismatch

Shipped 2026-11-12 · ⚠️ breaking · contract `3a4ff8dac458cf83` → `1.0` → `1.1`

Answers: no ask

## Each ask

No ask. This file covers the contract moving from `3a4ff8dac458cf83`, the last version the TUI read, through `1.0` and `1.1`.

## What changed

**1. `info.version` is two numbers, `breaking.adding` (`1.0`).** It is no longer a 16-digit hash. Breaking because a client that expects the hash form, or compares versions as hashes, reads a new shape.

- Before: `"info": {"version": "3a4ff8dac458cf83", …}`
- After: `"info": {"version": "1.1", …}`

The rule is in the published contract, *Base Conventions*:
- **The first number moves** when a change can break a client built against an earlier version: a route, field, enum value, error code, reason, status or media type removed or renamed; a type, format or default changed; a request field made required or a bound narrowed; a response field made optional; a variant added to a value a response sends; a login newly required.
- **The second number moves** on an addition, such as a route, an optional field, an enum value, an error code, a reason or a status, or on a rule loosened.
- **A wording edit moves neither number** and has no `x-changelog` entry.
- A client built against `X.Y` works against any `X.Z` with `Z` at least `Y`, provided it tolerates what an addition brings: unknown response fields, enum values, error codes, reasons and statuses.

The `x-changelog` entries older than `1.0` keep their 16-digit headings.

**2. `GET /health` answers `200` with more fields (`1.1`, additive).** It is still public and still carries no ledger data. Every field is always present, and is `null` when unknown.

```json
{
  "status": "ok",
  "release": "fc09f43",
  "contract_version": "1.1",
  "mode": "REAL",
  "structure": {"newest_update": "<the newest update's name>", "updates_recorded": 69, "fixes_recorded": 0},
  "backup": {"state": "missing", "time": null, "age_seconds": null}
}
```

- **`release`:** the version of the code the engine runs. It is a tag, or a tag plus the commits since it and a short commit id, with `-dirty` added when the code has uncommitted changes. It is `null` when it cannot be read. Until the first release is tagged, it is a short commit id, as above.
- **`contract_version`:** the same value as `info.version` in `GET /openapi.json`.
- **`mode`:** `"REAL"` for the owner's ledger, `"PRACTICE"` for a practice database.
- **`structure`:** the database's record of the updates made to its structure. `newest_update` is `null` when there are none. `updates_recorded` and `fixes_recorded` are counts.
- **`backup`:** the last good backup of the ledger.
  - `state` is one of:

    | `state` | Meaning |
    |---|---|
    | `"ok"` | a good backup exists |
    | `"overdue"` | older than 36 hours |
    | `"missing"` | no record of any backup |
    | `"unreadable"` | the record cannot be read |
    | `"future_dated"` | the record is dated more than 5 minutes ahead of the engine's clock |
    | `"not_kept"` | always for `PRACTICE`: a practice database has no backup |

  - `time` is the backup's time in UTC (`"2026-11-11T18:00:00Z"`). It is `null` for `missing`, `unreadable` and `not_kept`.
  - `age_seconds` is the backup's age in seconds. It is `null` for those three and for `future_dated`.
  - An old or missing backup never makes the answer `503`.
  - The live engine shows `"missing"` until the owner installs the new nightly backup.

**3. `GET /health` answers `503 SERVICE_UNAVAILABLE` also on a structure mismatch (`1.1`).** Before, it answered `503` only when the database was unreachable. Now it also does when the database's structure no longer matches the engine's code, for example when it was updated while the engine ran.

- The `message` says what is wrong and what to do, in words meant to be shown as sent.
- `fields`, `reasons` and `details` are `null`.

```json
{"error": {"code": "SERVICE_UNAVAILABLE", "message": "<what is wrong, and what to do>", "fields": null, "reasons": null, "details": null}}
```

**4. The engine refuses to start (`1.1`)** on a database whose structure does not match its code, and on any database that is neither the owner's ledger nor a practice database. A practice engine started that way never comes up: its start-up output names the problem and the fix.

## How it was checked

- **The engine's suite passed** at the commits that shipped `1.0` and `1.1`. It covers:
  - the version rule (a wording edit leaves `info.version` as it is, a new field moves the second number);
  - every `/health` field and backup state;
  - `503` on an unreachable database and on a database one structure update behind;
  - the refusal to start.
- **The live engine serves contract `1.1`.** On 2026-11-12 `GET /health` on it answered the example in "What changed" → 2: `mode` `"REAL"`, backup `"missing"`.
- **Not run against a practice engine for this hand-off.** On a practice engine `mode` is `"PRACTICE"` and `backup.state` is `"not_kept"`.

## What the TUI does

1. **Read `info.version` as `breaking.adding`.**
   - Store the version it was checked against, and compare.
   - A change in the first number means a change that can break the TUI.
   - A change in the second number alone is safe, as long as the TUI ignores response fields, enum values, error codes, reasons and statuses it does not know.
   - Its drift check stays as it is, with the version as an opaque string compared for equality.
2. **Show from `GET /health`:**
   - which database it talks to (`mode`: `REAL` or `PRACTICE`);
   - the backup's `state` and age (from `age_seconds`, or `time`);
   - optionally `release` and `contract_version`.
   - Treat any `null` as unknown, never as zero.
3. **On `503` from `GET /health`,** show `message` exactly as sent. It already says what to do.
4. **Restart the practice engine** so it runs the new code: `deploy/local/client-practice-engine.sh <port>`. If it does not come up, its start-up output names the fix.

## Done when

- The TUI accepts `"1.1"` as the contract version, and its drift check passes against it.
- The TUI shows `mode` and the backup's state and age from `GET /health`, against the practice engine (`PRACTICE`, `not_kept`).
- A `503` from `GET /health` shows its `message` as sent.
- The TUI confirms back that it has read up to `1.1`.
