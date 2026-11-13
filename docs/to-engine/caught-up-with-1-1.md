# Caught up with contract 1.1: the version is `breaking.adding`, and `GET /health` reports what the engine runs

2026-11-12

## Covers

The hand-off of 2026-11-12 ("The contract version is two numbers, and `GET /health` reports what
the engine runs and answers `503` on a structure mismatch"), contract `3a4ff8dac458cf83` → `1.0`
→ `1.1`, read in full. Checked against the practice engine serving `1.1`, started on its newest
code: the client's whole live contract suite ran green, 414 passed, plus 2 expected failures
waiting on the sheet import's built names.

## Done when, checked

- **The TUI accepts `"1.1"` as the contract version, and its drift check passes against it:**
  worked. The client recorded `1.1`, still compared as an opaque string; nothing in it assumed
  the 16-digit form.
- **`mode` and the backup's state and age from `GET /health`, against the practice engine:** read,
  not yet shown. A live test checks every field the contract lists. Fields the client doesn't know
  are tolerated, as Base Conventions asks. On the practice engine the test sees `mode` `PRACTICE`,
  `backup.state` `not_kept` with `time` and `age_seconds` both `null`, and `contract_version` equal
  to `info.version`. The screens that show them come in the client's next screen work, after its
  first release.
- **A `503` from `GET /health` shows its `message` as sent:** not yet. The contract lists `503` as
  an error response for `GET /health`. A structure mismatch can't be caused from the client, so
  the screen showing it comes with the same screen work, and the client's shared error display
  will show the `message` as sent.
- **The TUI confirms back that it has read up to `1.1`:** this reply.

## Contract problems found

None.

## Asks this closes

None: the hand-off answers no ask.
