# Probes on the practice engine clean up after themselves

Raised 2026-10-25.

## Why

The practice engine (`:8002`, over the `expense_world_test` database) has one practice user,
shared by the terminal client's live contract suite, its hand checks of the app, and the engine
side's own hand-run probes. On 2026-10-25 that user held about 60 accounts, 55 reconciliations
and a few categories and hashtags that no client test made: names such as `Card A PEN …`,
`Null twin …`, `EL-A …`, `probe-…`, `ACC SIG PEN …` and `acc-…-card-pen`, posted straight to
`/accounts` and `/reconciliations` by probes run from the engine side. Most held statement codes
(`SIG` among them), so they took codes the client's tests and hand checks need, and filled the
app's Reconciliations browse with accounts nobody uses.

The client's suite now fails any test that leaves a record behind, and the client has a tool
that removes records by name prefix; it removed these on the owner's word. But the practice user
fills up again whenever a probe leaves its records.

## The ask

Every probe run against the practice engine removes what it creates before it ends, in reverse
dependency order (unarchive, revert, delete each statement once, delete transactions, then
hashtags, categories and accounts), or runs as a practice user of its own, never the shared one.
A probe that cannot clean up names its records with one fixed prefix, so they can be found and
removed together.

## Done when

- After any engine-side probe, the shared practice user holds no record the probe made.
- Engine-side probe code that writes to `:8002` either cleans up or uses its own user.

## What this client removes once it lands

Nothing: the client keeps its own leak check and cleanup tool for leaks of its own. It stops
having to clean up records it did not make.
