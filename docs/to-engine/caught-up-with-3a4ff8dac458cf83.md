# Caught up with contract 3a4ff8dac458cf83: an error's details, the new words, the soles-only sample and the live suite on several cash accounts

2026-11-11

## Covers

Part 1 of the reply to the hand-off of 2026-11-11 ("A loose-lines refusal names its lines by id
in `error.details`…"), contract `ebadad5b9499610c` to `3a4ff8dac458cf83`: everything but the
screens for several cash accounts (part 2) and the screen listing a refusal's loose lines
(part 3), which follow. Checked against the practice engine serving `3a4ff8dac458cf83`: the
client's whole live contract suite ran green, 408 passed, plus 2 expected failures waiting on
the sheet import's built names. No test waits on the loose-lines ask any more.

## Done when, checked

- **The `card-soles-only` contract test uploads to `BCP-0001` and closes it:** worked. The
  practice seed's soles-only account takes a statement code, the sample uploads to it and
  completes holding soles alone, with a difference of 0 and one line per row; the account is
  left as the seed made it.
- **A `null` `bank_code` sent to the cash account on edit shows `CASH_TAKES_NO_FIELD`:**
  worked, for `name`, `bank_code`, `current_number`, `new_number` and `statement_code`. A bank
  account's or person's `null` `bank_code` or `new_number` answers `NOT_NULL` alone, after a
  `null` `color` and after the `404`, as the contract orders it.
- **No client code or test matches an underscore noun in a message, or a `404` from the samples
  route:** worked. The client never matched either in its code; its tests now read refusals by
  code and reason, and read a message only for the data it alone carries.
- **A bank download refused `PERSON_TAKES_NO_STATEMENT` shows as a download for a person:**
  worked as the engine side goes: a download for a person is refused on `account_id`, dry run
  and apply, nothing written. The client shows it as it shows any refusal of a download, the
  engine's words under the key. The race itself (`make-person` landing during the download)
  was not forced from the client.
- **The client reads `3a4ff8dac458cf83` from `/openapi.json` with no open catch-up:** worked.
- **Three cash creates and an empty one deleting:** worked in the live suite (names `CASH-<n>`
  in rising order, a number never reused, one held by another account's name skipped, an empty
  account deleted, one holding its opening balance refused `HAS_TRANSACTIONS`). The client's
  screens for it are part 2.

## Contract problems found

- **`details` has no published shape.** `ErrorBody.details` is an open object
  (`additionalProperties: true`); `bank_line_ids` and `count` appear only in the prose of
  `POST /statements/{id}/complete` and `POST /statements/import`, so a client cannot check the
  keys it reads against the schema. Raised as its own ask, "An error's `details` has a published
  shape for each refusal that carries one".

## Asks this closes

- "`card-soles-only` cannot be tested"
- "The bound is written two ways"
- "`POST /auth/pat`: the taken-id message differs from the contract"
- "`null` on the cash account answers two codes for one mistake"
- "PUT's null rule leaves out the cash account's `name`"
