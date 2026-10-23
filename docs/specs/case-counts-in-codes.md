# Letter case counts in an operation code and a statement line

**Status: draft (orchestrator, 2026-10-22), for the owner's approval.** A catch-up spec: it folds
in the engine's hand-off "The contract states that letter case counts in an operation code and a
statement line" (shipped 2026-10-22). Nothing on screen changes.

---

## Why

The last reply to the engine asked whether `SIG-202603-029` and `sig-202603-029` are one
statement line or two. The engine answers with the owner's rule (2026-10-22): a field a person
types, a name, is compared without regard to case; a field that comes from the bank or from a
program, an operation code or a statement line, is compared exactly. The engine already behaved
this way, and so does the app: the sheet import groups rows by the exact `COD_EECC` text, and a
bank file's operation numbers are compared as written. The contract now says so, in a new
version, and the app has to move to it.

## What it must do

- The app holds the engine's new contract version, so the version check passes again.
- The app never folds case when it compares an operation code or a statement line, and a test
  says so, so it cannot drift.

## How the owner knows it is done

1. The version check reports no change against the practice engine.
2. The unit and live tests pass, including the new ones below.

## Catching up with the engine

**Catches up to contract `996986490b68f05e`:** every contract change after `54fd1012f7d60abc`
up to it. Both changes are wording only: case counts in an operation code and a statement line
(stated in POST /v1/transactions, PUT /v1/transactions/{id}, POST /v1/transactions/batch,
POST /v1/transactions/import and the texts of `OPERATION_CODE_EXISTS`, `STATEMENT_LINE_EXISTS`
and `DUPLICATE_IN_REQUEST`), and the contract says "operation code" wherever it means one, "the
line's code" meaning only `line_code`. This repo's docs and comments already use that wording.

**The engine's checks** — its "Done when". The tester's acceptance check runs it, and the reply
reports the result.

1. The TUI holds contract `996986490b68f05e`.

**What the engine declined:** nothing. It answered the reply's question and widened it to
operation codes, which the contract was just as silent about.

**Questions for the owner:** none open.

## Tasks

Drafted 2026-10-22; wait for the owner's approval. None draws a screen.

1. **The app holds contract `996986490b68f05e`.** Recorded with the drift script's
   `--record-version` against the practice engine. Passes if
   [scripts/engine-contract-version](../../scripts/engine-contract-version) holds
   `996986490b68f05e` and nothing else, the drift script against `:8002` reports no change and no
   fixture key the engine does not serve, and the live contract-citation test passes. The
   engine's check 1 and the owner's check 1.
2. **A unit test pins exact comparison in both importers.** Sheet rows whose `COD_EECC` differ
   only in case (`SIG-1`, `sig-1`) make two statement lines, never one group; a bank file holding
   operations `abc123` and `ABC123` keeps both rows, neither refused as appearing twice. Passes if
   both tests pass and fail when the comparison is case-folded.
3. **The live contract suite pins the stated rule.** With `SIG-…` on a live line, a create with
   the same statement line in lower case lands on a different bank line, and with `ABC…` live on
   an account, the same operation code in lower case on that account lands too; all four read
   back as sent from `GET /transactions/{id}` and `GET /bank-lines/{id}`. The exact same values
   again are refused `409` with `STATEMENT_LINE_EXISTS` on `statement_line` and
   `OPERATION_CODE_EXISTS` on `operation_code`, writing nothing. Each new test cites the contract
   part stating the rule. Passes if the tests pass against `:8002`.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `54fd1012f7d60abc` (exclusive) to `996986490b68f05e` (inclusive), the
  hand-off named above. `996986490b68f05e` is the version to start the next catch-up file from.
- **Done when, checked:** the engine's check above, with the tester's result.
- **Contract problems found:** what the build and the tester's run find; "none" when none.
- **Asks this closes:** none as an ask file; it answers "Whether case counts in a statement line
  is unstated" from the reply for contract `54fd1012f7d60abc`.
