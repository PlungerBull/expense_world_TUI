# The contract says what each version changed

Raised 2026-09-27 by the CLI client.

## Why

`GET /openapi.json` carries a version (`info.version`) that moves on any change, but it does
not say what the change was. Clients save only the version they last checked, so they can tell
*that* the contract moved, never *what* moved. The only other ways to find out are keeping a
whole copy of the contract to diff, or reading the engine's source folder. Clients are not
allowed to read the engine's folder, and a saved copy goes stale and gets reinvented slightly
differently in each client (CLI, web, iOS).

## The ask

The published contract carries a change log. Each entry is a version plus the endpoints,
rules and error codes it added, changed or removed, in plain words. A client that knows the
version it last checked can then list everything that happened between that version and the
current one.

It lives in the contract itself (for example an `x-changelog` extension at the top level of
`openapi.json`), so it needs no login and no access to the engine's folder, like the rest of the
contract.

## Done when

- Every change that moves `info.version` adds a change-log entry for the new version. The
  engine's tests fail if the version moves with no matching entry.
- Each entry names what was added, changed or removed (endpoint, rule section or error code)
  in words a client developer can act on, without file paths or internal names.
- A client can read, from the contract alone, every entry newer than a version it holds.

## What the CLI removes once it lands

Its fallback for "the engine changed": today it can only report which of its own test fixtures
no longer match the new contract. With the change log it lists the engine's own entries instead.
